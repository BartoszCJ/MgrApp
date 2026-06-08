"""Heurystyka: detekcja kontaktu z Tornado Cash.

Co to robi:
- laduje liste znanych adresow Tornado Cash z `data/known_addresses/tornado_cash.json`,
- dla podanego adresu root i listy transakcji wykrywa:
  - deposit: `to_address` == Tornado pool/router,
  - withdraw: `from_address` == Tornado pool/router,
- zwraca liste Alert.

Co to znaczy w praktyce:
- Deposit do Tornado = moment ukrycia srodkow. Dalsze sledzenie po grafie sie konczy.
- Withdraw z Tornado = adres pojawia sie z 'nikad', srodki "czyste" - ale wciaz Tornado-tainted.
- Tornado jest na liscie sankcji OFAC od 2022-08-08, kazda interakcja jest sygnalem.

Te alerty bezposrednio realizuja cel pracy magisterskiej:
"wykrywanie metod ukrywania pochodzenia srodkow (mixing, hopping, bridging)".
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from loguru import logger

from forensics.core.models import Alert, Transaction

# data/known_addresses/tornado_cash.json relatywnie do tego pliku:
# heuristics/tornado.py -> ../../../../data/known_addresses/tornado_cash.json
_DATA_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data"
    / "known_addresses"
    / "tornado_cash.json"
)


@lru_cache(maxsize=1)
def _load_tornado_db() -> dict[str, dict]:
    """Laduje JSON z adresami Tornado i zwraca slownik adres_lowercase -> metadata."""
    if not _DATA_PATH.exists():
        logger.warning("Brak pliku Tornado Cash: {}", _DATA_PATH)
        return {}

    raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    addresses = {}
    for entry in raw.get("addresses", []):
        addr = entry["address"].lower()
        addresses[addr] = entry
    logger.info("Zaladowano {} adresow Tornado Cash", len(addresses))
    return addresses


def detect_tornado(transactions: list[Transaction], root_address: str) -> list[Alert]:
    """Generuje alerty Tornado dla transakcji sledzonego adresu.

    Args:
        transactions: pelen zestaw tx z grafu BFS (ETH + ERC-20), nie tylko roota.
        root_address: adres glowny trace (kontekst). Heurystyka analizuje CALY graf -
            alert wskazuje observed_address (kto dotknal Tornado), a metadata.is_root
            mowi czy to root, czy adres posredni z grafu.

    Returns:
        lista Alert posortowana wg block_number (najnowsze pierwsze).
    """
    db = _load_tornado_db()
    if not db:
        return []

    root = root_address.lower()
    alerts: list[Alert] = []
    # Grupujemy per (pula Tornado, kierunek, obserwowany adres). Obserwowany adres to
    # strona NIE-Tornado: przy deposit nadawca, przy withdraw odbiorca. Dzieki temu
    # lapiemy tez adresy posrednie z grafu BFS, nie tylko bezposredni kontakt roota.
    seen: dict[tuple[str, str, str], dict] = {}

    for tx in transactions:
        from_addr = tx.from_address.lower()
        to_addr = (tx.to_address or "").lower()

        for counterparty, observed, direction in (
            (to_addr, from_addr, "deposit"),
            (from_addr, to_addr, "withdraw"),
        ):
            if not counterparty or counterparty not in db:
                continue
            # observed musi istniec i nie byc samym Tornado (pomija Tornado->Tornado)
            if not observed or observed in db:
                continue

            meta = db[counterparty]
            key = (counterparty, direction, observed)
            bucket = seen.setdefault(
                key,
                {
                    "observed": observed,
                    "count": 0,
                    "first_block": tx.block_number,
                    "last_block": tx.block_number,
                    "tx_hashes": [],
                    "total_value": 0.0,
                    "asset": meta.get("asset") or tx.token_symbol or "?",
                    "kind": meta.get("kind", "pool"),
                    "denomination": meta.get("denomination"),
                },
            )
            bucket["count"] += 1
            bucket["first_block"] = min(bucket["first_block"], tx.block_number)
            bucket["last_block"] = max(bucket["last_block"], tx.block_number)
            bucket["tx_hashes"].append(tx.hash)
            bucket["total_value"] += tx.value_eth

    for (counterparty, direction, observed), agg in seen.items():
        denom = agg["denomination"]
        asset = agg["asset"]
        kind = agg["kind"]
        count = agg["count"]
        is_root = observed == root
        short = f"{observed[:6]}...{observed[-4:]}"
        who = "Sledzony adres (root)" if is_root else f"Adres posredni {short}"
        via = "" if is_root else f" przez {short}"

        denom_str = f"pula {denom} {asset}" if kind == "pool" and denom is not None else kind

        if direction == "deposit":
            title = f"Deposit do Tornado Cash{via} ({denom_str}, {count} tx)"
            message = (
                f"{who} wyslal srodki do Tornado Cash ({denom_str}). "
                f"To moment ukrycia srodkow - mixer zacieta dalsze sledzenie po grafie. "
                f"Tornado Cash jest na liscie sankcji OFAC od 2022-08-08."
            )
        else:
            title = f"Withdraw z Tornado Cash{via} ({denom_str}, {count} tx)"
            message = (
                f"{who} otrzymal srodki z Tornado Cash ({denom_str}). "
                f"Srodki sa Tornado-tainted (powiazane z mixerem). "
                f"Klasyczny sygnal pranie krypto."
            )

        alerts.append(
            Alert(
                type=f"tornado_cash_{direction}",
                severity="critical",
                title=title,
                message=message,
                related_addresses=[observed, counterparty],
                related_tx_hashes=agg["tx_hashes"][:5],  # max 5 zeby nie zalewac UI
                metadata={
                    "observed_address": observed,
                    "is_root": is_root,
                    "tornado_kind": kind,
                    "asset": asset,
                    "denomination": denom,
                    "tx_count": count,
                    "first_block": agg["first_block"],
                    "last_block": agg["last_block"],
                    "total_value_normalized": round(agg["total_value"], 4),
                },
            )
        )

    # najnowsze pierwsze
    alerts.sort(key=lambda a: a.metadata.get("last_block", 0), reverse=True)
    return alerts
