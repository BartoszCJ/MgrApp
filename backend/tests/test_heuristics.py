"""Testy heurystyk Tornado/CEX na PELNYM grafie BFS (nie tylko root_address).

Regresja na buga: heurystyki wczesniej lapaly tylko bezposredni kontakt roota,
przez co root -> posrednik -> Tornado/CEX nie dawalo alertu (i metryki = 0%).
"""

from __future__ import annotations

from datetime import UTC, datetime

from forensics.core.models import Transaction
from forensics.heuristics.known_address import detect_known_group
from forensics.heuristics.tornado import detect_tornado

ROOT = "0x" + "1" * 40
INTERMEDIATE = "0x" + "2" * 40
# Realne adresy z data/known_addresses/
TORNADO_POOL = "0xA160cdAB225685dA1d56aa342Ad8841c3b53f291"  # Tornado 100 ETH pool
BINANCE = "0x28C6c06298d514Db089934071355E5743bf21d60"  # Binance 14


def _tx(
    from_addr: str,
    to_addr: str,
    value: float = 1.0,
    block: int = 100,
    token: str | None = None,
) -> Transaction:
    return Transaction(
        hash=f"0x{from_addr[-4:]}{to_addr[-4:]}{block}",
        block_number=block,
        timestamp=datetime.now(UTC),
        from_address=from_addr,
        to_address=to_addr,
        value_wei=str(int(value * 10**18)),
        value_eth=value,
        token_symbol=token,
    )


def test_tornado_detects_deposit_via_intermediate() -> None:
    """root -> posrednik -> Tornado: alert wskazuje posrednika, is_root=False."""
    txs = [
        _tx(ROOT, INTERMEDIATE, value=10, block=100),
        _tx(INTERMEDIATE, TORNADO_POOL, value=9, block=110),
    ]

    deposits = [a for a in detect_tornado(txs, ROOT) if a.type == "tornado_cash_deposit"]

    assert len(deposits) == 1
    alert = deposits[0]
    assert alert.metadata["observed_address"] == INTERMEDIATE.lower()
    assert alert.metadata["is_root"] is False
    assert TORNADO_POOL.lower() in [a.lower() for a in alert.related_addresses]


def test_tornado_detects_direct_root_deposit() -> None:
    """root -> Tornado bezposrednio: is_root=True."""
    txs = [_tx(ROOT, TORNADO_POOL, value=5, block=100)]

    deposits = [a for a in detect_tornado(txs, ROOT) if a.type == "tornado_cash_deposit"]

    assert len(deposits) == 1
    assert deposits[0].metadata["is_root"] is True
    assert deposits[0].metadata["observed_address"] == ROOT.lower()


def test_cex_detects_deposit_via_intermediate() -> None:
    """root -> posrednik -> CEX: alert cex_outgoing wskazuje posrednika, nazwa zachowana."""
    txs = [
        _tx(ROOT, INTERMEDIATE, value=10, block=100),
        _tx(INTERMEDIATE, BINANCE, value=9, block=120),
    ]

    cex = [a for a in detect_known_group(txs, ROOT, "cex.json") if a.type == "cex_outgoing"]

    assert len(cex) == 1
    assert cex[0].metadata["observed_address"] == INTERMEDIATE.lower()
    assert cex[0].metadata["is_root"] is False
    assert cex[0].metadata["name"]  # nazwa gieldy potrzebna dla metryki cex_coverage


def test_heuristics_ignore_unrelated_transfers() -> None:
    """Brak kontaktu z Tornado/CEX = brak alertow (nie generujemy szumu)."""
    other = "0x" + "9" * 40
    txs = [
        _tx(ROOT, INTERMEDIATE, value=1, block=100),
        _tx(INTERMEDIATE, other, value=1, block=101),
    ]

    assert detect_tornado(txs, ROOT) == []
    assert detect_known_group(txs, ROOT, "cex.json") == []
