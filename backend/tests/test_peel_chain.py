"""Testy heurystyki peel chain."""

from __future__ import annotations

from datetime import UTC, datetime

from forensics.core.models import Transaction
from forensics.heuristics.peel_chain import detect_peel_chain


def _tx(
    block: int,
    from_addr: str,
    to_addr: str,
    value: float,
    token: str | None = None,
    tx_hash: str | None = None,
) -> Transaction:
    return Transaction(
        hash=tx_hash or f"0x{block:064x}",
        block_number=block,
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        from_address=from_addr,
        to_address=to_addr,
        value_wei=str(int(value * 1e18)),
        value_eth=value,
        token_symbol=token,
    )


PEELER = "0x" + "a" * 40
ROOT = "0x" + "f" * 40
CHANGE_DEST = "0x" + "b" * 40
PEEL_DEST_1 = "0x" + "c" * 40
PEEL_DEST_2 = "0x" + "d" * 40
PEEL_DEST_3 = "0x" + "e" * 40


def test_detects_classic_peel_chain() -> None:
    """1 duza change (80%) + 3 male peels do 3 roznych adresow -> alert."""
    txs = [
        _tx(100, PEELER, CHANGE_DEST, 80.0, tx_hash="0xmain"),
        _tx(101, PEELER, PEEL_DEST_1, 7.0, tx_hash="0xpeel1"),
        _tx(102, PEELER, PEEL_DEST_2, 7.0, tx_hash="0xpeel2"),
        _tx(103, PEELER, PEEL_DEST_3, 6.0, tx_hash="0xpeel3"),
    ]
    alerts = detect_peel_chain(txs, root_address=ROOT)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.type == "peel_chain"
    assert alert.severity == "warning"
    assert alert.metadata["peeler"] == PEELER
    assert alert.metadata["peel_count"] == 3
    assert alert.metadata["unique_peel_recipients"] == 3
    assert alert.metadata["main_share"] >= 0.6
    assert alert.metadata["is_root_peeler"] is False


def test_skips_when_main_share_too_low() -> None:
    """Wszystkie tx mniej-wiecej rownej wartosci -> to nie peel chain, tylko splitter."""
    txs = [
        _tx(100, PEELER, CHANGE_DEST, 25.0),
        _tx(101, PEELER, PEEL_DEST_1, 25.0),
        _tx(102, PEELER, PEEL_DEST_2, 25.0),
        _tx(103, PEELER, PEEL_DEST_3, 25.0),
    ]
    alerts = detect_peel_chain(txs, root_address=ROOT)
    assert alerts == []


def test_skips_when_too_few_outgoing() -> None:
    """2 tx to za malo na peel chain."""
    txs = [
        _tx(100, PEELER, CHANGE_DEST, 90.0),
        _tx(101, PEELER, PEEL_DEST_1, 10.0),
    ]
    alerts = detect_peel_chain(txs, root_address=ROOT)
    assert alerts == []


def test_skips_when_peels_go_to_same_recipient() -> None:
    """Wymagamy >=2 roznych odbiorcow peeli - inaczej to splitter do jednego adresu."""
    txs = [
        _tx(100, PEELER, CHANGE_DEST, 80.0),
        _tx(101, PEELER, PEEL_DEST_1, 7.0),
        _tx(102, PEELER, PEEL_DEST_1, 7.0),
        _tx(103, PEELER, PEEL_DEST_1, 6.0),
    ]
    alerts = detect_peel_chain(txs, root_address=ROOT)
    assert alerts == []


def test_skips_when_window_too_wide() -> None:
    """Tx rozjechane przez 50000 blokow to nie spojny peel."""
    txs = [
        _tx(100, PEELER, CHANGE_DEST, 80.0),
        _tx(20000, PEELER, PEEL_DEST_1, 7.0),
        _tx(40000, PEELER, PEEL_DEST_2, 7.0),
        _tx(60000, PEELER, PEEL_DEST_3, 6.0),
    ]
    alerts = detect_peel_chain(txs, root_address=ROOT)
    assert alerts == []


def test_marks_root_peeler() -> None:
    """Gdy sam root robi peel - is_root_peeler=True (do podswietlenia w UI)."""
    txs = [
        _tx(100, ROOT, CHANGE_DEST, 80.0, tx_hash="0xmain"),
        _tx(101, ROOT, PEEL_DEST_1, 7.0, tx_hash="0xpeel1"),
        _tx(102, ROOT, PEEL_DEST_2, 7.0, tx_hash="0xpeel2"),
        _tx(103, ROOT, PEEL_DEST_3, 6.0, tx_hash="0xpeel3"),
    ]
    alerts = detect_peel_chain(txs, root_address=ROOT)
    assert len(alerts) == 1
    assert alerts[0].metadata["is_root_peeler"] is True


def test_separates_by_token() -> None:
    """Peel chain w ETH i osobno w USDC = 2 alerty (nie mieszamy tokenow)."""
    txs = [
        # ETH peel
        _tx(100, PEELER, CHANGE_DEST, 80.0, tx_hash="0xe1"),
        _tx(101, PEELER, PEEL_DEST_1, 7.0, tx_hash="0xe2"),
        _tx(102, PEELER, PEEL_DEST_2, 7.0, tx_hash="0xe3"),
        _tx(103, PEELER, PEEL_DEST_3, 6.0, tx_hash="0xe4"),
        # USDC peel w tym samym oknie
        _tx(200, PEELER, CHANGE_DEST, 8000.0, token="USDC", tx_hash="0xu1"),
        _tx(201, PEELER, PEEL_DEST_1, 700.0, token="USDC", tx_hash="0xu2"),
        _tx(202, PEELER, PEEL_DEST_2, 700.0, token="USDC", tx_hash="0xu3"),
        _tx(203, PEELER, PEEL_DEST_3, 600.0, token="USDC", tx_hash="0xu4"),
    ]
    alerts = detect_peel_chain(txs, root_address=ROOT)
    assert len(alerts) == 2
    tokens = {a.metadata["token"] for a in alerts}
    assert tokens == {"ETH", "USDC"}


def test_dedups_overlapping_windows() -> None:
    """4 tx w jednym oknie - 1 alert, nie 2 (overlapping sliding windows)."""
    txs = [
        _tx(100, PEELER, CHANGE_DEST, 80.0, tx_hash="0xmain"),
        _tx(101, PEELER, PEEL_DEST_1, 7.0),
        _tx(102, PEELER, PEEL_DEST_2, 7.0),
        _tx(103, PEELER, PEEL_DEST_3, 6.0),
    ]
    alerts = detect_peel_chain(txs, root_address=ROOT)
    assert len(alerts) == 1
