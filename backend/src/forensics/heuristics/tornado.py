"""Heurystyka: detekcja kontaktu z Tornado Cash.

Co to robi:
- laduje liste znanych adresow Tornado Cash z `data/known_addresses/tornado_cash.json`,
- dla podanego adresu root i listy transakcji:
  - jesli `to_address` == Tornado pool/router -> deposit (sledzony adres oddaje srodki do mieszalni),
  - jesli `from_address` == Tornado pool/router -> withdraw (sledzony adres dostaje srodki z mieszalni),
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
        transactions: lista transakcji zwrocona przez Etherscan (txlist + tokentx).
        root_address: adres ktorego dotyczy trace (do wskazania kierunku ruchu).

    Returns:
        lista Alert posortowana wg block_number (najnowsze pierwsze).
    """
    db = _load_tornado_db()
    if not db:
        return []

    root = root_address.lower()
    alerts: list[Alert] = []
    # Grupowanie wielu transakcji do tego samego puli w jeden alert (zmniejsza spam)
    seen: dict[tuple[str, str], dict] = {}

    for tx in transactions:
        from_addr = tx.from_address.lower()
        to_addr = (tx.to_address or "").lower()

        for counterparty, direction in (
            (to_addr, "deposit"),
            (from_addr, "withdraw"),
        ):
            if not counterparty or counterparty not in db:
                continue
            # Filtruj wlasciwy kierunek: deposit = my -> tornado, withdraw = tornado -> my
            if direction == "deposit" and from_addr != root:
                continue
            if direction == "withdraw" and to_addr != root:
                continue

            meta = db[counterparty]
            key = (counterparty, direction)
            bucket = seen.setdefault(
                key,
                {
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

    for (counterparty, direction), agg in seen.items():
        denom = agg["denomination"]
        asset = agg["asset"]
        kind = agg["kind"]
        count = agg["count"]

        if kind == "pool" and denom is not None:
            denom_str = f"pula {denom} {asset}"
        else:
            denom_str = f"{kind}"

        if direction == "deposit":
            title = f"Deposit do Tornado Cash ({denom_str}, {count} tx)"
            message = (
                f"Sledzony adres wyslal srodki do Tornado Cash ({denom_str}). "
                f"To moment ukrycia srodkow - mixer zacieta dalsze sledzenie po grafie. "
                f"Tornado Cash jest na liscie sankcji OFAC od 2022-08-08."
            )
        else:
            title = f"Withdraw z Tornado Cash ({denom_str}, {count} tx)"
            message = (
                f"Sledzony adres otrzymal srodki z Tornado Cash ({denom_str}). "
                f"Srodki sa Tornado-tainted (powiazane z mixerem). "
                f"Klasyczny sygnal pranie krypto."
            )

        alerts.append(
            Alert(
                type=f"tornado_cash_{direction}",
                severity="critical",
                title=title,
                message=message,
                related_addresses=[counterparty],
                related_tx_hashes=agg["tx_hashes"][:5],  # max 5 zeby nie zalewac UI
                metadata={
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
