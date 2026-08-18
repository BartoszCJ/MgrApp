
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from loguru import logger

from forensics.core.models import Alert, Transaction

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "known_addresses"


@lru_cache(maxsize=8)
def _load_group(filename: str) -> tuple[str, str, dict[str, dict]]:
    """Zwraca (name, category, addresses_dict). Cache na nazwie pliku."""
    path = _DATA_DIR / filename
    if not path.exists():
        logger.warning("Brak pliku adresow: {}", path)
        return ("", "", {})

    raw = json.loads(path.read_text(encoding="utf-8"))
    name = raw.get("name", filename)
    category = raw.get("category", "labeled")
    addresses = {entry["address"].lower(): entry for entry in raw.get("addresses", [])}
    logger.info("Zaladowano {} adresow z grupy '{}'", len(addresses), name)
    return (name, category, addresses)


def detect_known_group(
    transactions: list[Transaction],
    root_address: str,
    filename: str,
    severity: str = "warning",
) -> list[Alert]:
    """Wykrywa kontakt sledzonego adresu z grupa znanych adresow.

    Args:
        transactions: lista transakcji do przeskanowania.
        root_address: adres podstawowy trace (zeby okreslic kierunek).
        filename: np. "bridges.json" lub "cex.json" w data/known_addresses/.
        severity: severity alertu (warning dla bridges, warning/info dla CEX).
    """
    group_name, category, db = _load_group(filename)
    if not db:
        return []

    root = root_address.lower()
    # Klucz: (znany adres, kierunek, obserwowany adres). Obserwowany to strona NIE-znana:
    # przy outgoing nadawca, przy incoming odbiorca. Lapiemy adresy posrednie z grafu BFS,
    # nie tylko bezposredni kontakt roota.
    seen: dict[tuple[str, str, str], dict] = {}

    for tx in transactions:
        from_addr = tx.from_address.lower()
        to_addr = (tx.to_address or "").lower()

        for counterparty, observed, direction in (
            (to_addr, from_addr, "outgoing"),
            (from_addr, to_addr, "incoming"),
        ):
            if not counterparty or counterparty not in db:
                continue
            # observed musi istniec i nie byc samym znanym adresem (pomija endpoint->endpoint)
            if not observed or observed in db:
                continue

            key = (counterparty, direction, observed)
            bucket = seen.setdefault(
                key,
                {
                    "observed": observed,
                    "name": db[counterparty].get("name", counterparty),
                    "count": 0,
                    "tx_hashes": [],
                    "total_value": 0.0,
                    "first_block": tx.block_number,
                    "last_block": tx.block_number,
                    "tokens": set(),
                },
            )
            bucket["count"] += 1
            bucket["tx_hashes"].append(tx.hash)
            bucket["total_value"] += tx.value_eth
            bucket["first_block"] = min(bucket["first_block"], tx.block_number)
            bucket["last_block"] = max(bucket["last_block"], tx.block_number)
            if tx.token_symbol:
                bucket["tokens"].add(tx.token_symbol)

    alerts: list[Alert] = []
    for (counterparty, direction, observed), agg in seen.items():
        is_root = observed == root
        short = f"{observed[:6]}...{observed[-4:]}"
        who = "Sledzony adres (root)" if is_root else f"Adres posredni {short}"
        via = "" if is_root else f" (przez {short})"
        tokens_str = ", ".join(sorted(agg["tokens"])) or "ETH"
        direction_pl = "do" if direction == "outgoing" else "z"
        verb_pl = "wyslal srodki" if direction == "outgoing" else "otrzymal srodki"

        if category == "bridge":
            title = f"Kontakt z bridge: {agg['name']}{via} ({agg['count']} tx, {tokens_str})"
            message = (
                f"{who} {verb_pl} {direction_pl} bridge'a {agg['name']}. "
                f"Klasyczny hopping cross-chain - srodki moga byc teraz na innym chainie. "
                f"Wymaga sledzenia na drugim koncu bridge."
            )
        elif category == "cex":
            title = f"Kontakt z CEX: {agg['name']}{via} ({agg['count']} tx, {tokens_str})"
            if direction == "outgoing":
                message = (
                    f"{who} zdeponowal srodki na giełde {agg['name']}. "
                    f"To moment cashout - dalsze sledzenie wymaga subpoeny do giełdy."
                )
            else:
                message = (
                    f"{who} dostal srodki z giełdy {agg['name']} (withdrawal). "
                    f"Mozliwe finansowanie operacji z konta KYC."
                )
        else:
            title = f"Kontakt z {group_name}: {agg['name']}{via} ({agg['count']} tx)"
            message = f"{who} {verb_pl} {direction_pl} {agg['name']}."

        alerts.append(
            Alert(
                type=f"{category}_{direction}",
                severity=severity,
                title=title,
                message=message,
                related_addresses=[observed, counterparty],
                related_tx_hashes=agg["tx_hashes"][:5],
                metadata={
                    "observed_address": observed,
                    "is_root": is_root,
                    "group": group_name,
                    "name": agg["name"],
                    "tokens": sorted(agg["tokens"]),
                    "tx_count": agg["count"],
                    "first_block": agg["first_block"],
                    "last_block": agg["last_block"],
                    "total_value_normalized": round(agg["total_value"], 4),
                },
            )
        )

    alerts.sort(key=lambda a: a.metadata.get("last_block", 0), reverse=True)
    return alerts
