"""Heurystyka: detekcja peel chain (hopping z odcinaniem kawalkow).

Co to robi:
- skanuje wszystkie transakcje z grafu BFS,
- grupuje wychodzace tx per (from_address, token),
- w przesuwnym oknie blokowym szuka wzorca:
  * >= 3 transakcji wychodzacych w bliskim oknie czasu,
  * jedna "change" tx >= 60% sumy wartosci okna,
  * pozostale "peels" trafiaja do co najmniej 2 roznych odbiorcow.

Co to znaczy w praktyce:
- Klasyczny obfuscation pattern. Adres dostaje duzy inflow, potem rozprowadza:
  jedna duza tx idzie dalej (change), kilka malych do nowych adresow (peels).
- Tak prano srodki z Ronin Bridge ($625M) i Nomad Bridge ($190M).
- W przeciwienstwie do Tornado/mixerow, peel chain dziala "na widoku" - kluczowe
  zeby algorytm umial to rozpoznac. To dokladnie pokrywa "hopping" z celu pracy:
  "wykrywanie metod ukrywania pochodzenia srodkow (mixing, hopping, bridging)".

Ograniczenia:
- BFS zbiera ograniczona liczbe tx per adres (per_hop_max_tx, domyslnie 20).
  W realnym peel chain bywa kilkadziesiat hopow - my zlapiemy poczatkowe kilka.
- Tresholdy sa empiryczne (block_window=5000 ~ 16h ETH, main_share=0.6).
  Do walidacji w rozdziale eksperymentow pracy.
"""

from __future__ import annotations

from collections import defaultdict

from forensics.core.models import Alert, Transaction


def _short(addr: str) -> str:
    """Skrocony adres do tytulu alertu, np. 0x1234...abcd."""
    if len(addr) < 12:
        return addr
    return f"{addr[:6]}...{addr[-4:]}"


def detect_peel_chain(
    transactions: list[Transaction],
    root_address: str,
    block_window: int = 5000,
    min_outgoing: int = 3,
    main_share_threshold: float = 0.6,
    min_unique_peels: int = 2,
) -> list[Alert]:
    """Wykrywa peel chain candidates w zbiorze transakcji.

    Args:
        transactions: pelen zestaw tx z grafu BFS (ETH + ERC-20).
        root_address: adres glowny (do oznaczenia czy peeler to root czy posredni).
        block_window: max rozpietosc blokow w oknie (5000 ~ 16h na ETH).
        min_outgoing: min liczba tx wychodzacych w oknie zeby uznac za candidate.
        main_share_threshold: jaka czesc sumy musi byc w jednej "change" tx (0.6 = 60%).
        min_unique_peels: min liczba roznych odbiorcow w malych transferach.

    Returns:
        Lista alertow severity=warning posortowana po block_number malejaco.
    """
    # Grupuj wychodzace tx per (nadawca, token) - peel chain to zawsze ten sam token.
    by_address_token: dict[tuple[str, str], list[Transaction]] = defaultdict(list)
    for tx in transactions:
        if tx.is_error:
            continue
        if not tx.from_address or not tx.to_address:
            continue
        if tx.value_eth <= 0:
            continue
        token_key = tx.token_symbol or "ETH"
        by_address_token[(tx.from_address.lower(), token_key)].append(tx)

    root = root_address.lower()
    alerts: list[Alert] = []
    # Dedup overlapping okien: ten sam (addr, token, main_tx_hash) -> jeden alert.
    seen_signatures: set[tuple[str, str, str]] = set()

    for (addr, token), txs in by_address_token.items():
        if len(txs) < min_outgoing:
            continue

        txs.sort(key=lambda t: t.block_number)

        # Przesuwne okno: dla kazdego startowego i zbieramy tx az do block_window.
        for i in range(len(txs) - min_outgoing + 1):
            window: list[Transaction] = [txs[i]]
            for j in range(i + 1, len(txs)):
                if txs[j].block_number - txs[i].block_number > block_window:
                    break
                window.append(txs[j])

            if len(window) < min_outgoing:
                continue

            main_tx = max(window, key=lambda t: t.value_eth)
            total_value = sum(t.value_eth for t in window)
            if total_value <= 0:
                continue

            main_share = main_tx.value_eth / total_value
            if main_share < main_share_threshold:
                continue

            peels = [t for t in window if t.hash != main_tx.hash]
            unique_recipients = {(t.to_address or "").lower() for t in peels}
            unique_recipients.discard("")
            if len(unique_recipients) < min_unique_peels:
                continue

            sig = (addr, token, main_tx.hash)
            if sig in seen_signatures:
                continue
            seen_signatures.add(sig)

            peel_value = total_value - main_tx.value_eth
            first_block = min(t.block_number for t in window)
            last_block = max(t.block_number for t in window)
            is_root_peeler = addr == root

            who = "Sledzony adres" if is_root_peeler else f"Adres {_short(addr)}"
            title = (
                f"Peel chain candidate: {_short(addr)} "
                f"({len(peels)} peels + 1 change, {token})"
            )
            message = (
                f"{who} w oknie ~{last_block - first_block} blokow wyslal "
                f"{len(window)} tx w {token}. Jedna duza tx "
                f"({main_tx.value_eth:.4f} {token} = {main_share * 100:.0f}% sumy okna) "
                f"kontynuuje przeplyw, {len(peels)} malych tx odcina "
                f"{peel_value:.4f} {token} do {len(unique_recipients)} roznych adresow. "
                f"Klasyczny pattern peel chain: glowny strumien idzie dalej jako 'change', "
                f"a male kawalki sa rozprowadzane na nowe adresy zeby utrudnic sledzenie."
            )

            related_addresses = [addr, *sorted(unique_recipients)]
            related_tx_hashes = [main_tx.hash, *[t.hash for t in peels[:4]]]

            alerts.append(
                Alert(
                    type="peel_chain",
                    severity="warning",
                    title=title,
                    message=message,
                    related_addresses=related_addresses[:6],
                    related_tx_hashes=related_tx_hashes[:5],
                    metadata={
                        "peeler": addr,
                        "is_root_peeler": is_root_peeler,
                        "token": token,
                        "main_tx_hash": main_tx.hash,
                        "main_value": round(main_tx.value_eth, 6),
                        "main_share": round(main_share, 3),
                        "peel_count": len(peels),
                        "peel_value": round(peel_value, 6),
                        "unique_peel_recipients": len(unique_recipients),
                        "total_value": round(total_value, 6),
                        "first_block": first_block,
                        "last_block": last_block,
                        "block_span": last_block - first_block,
                    },
                )
            )

    alerts.sort(key=lambda a: a.metadata.get("last_block", 0), reverse=True)
    return alerts
