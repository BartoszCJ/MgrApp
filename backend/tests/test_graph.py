"""Testy budowania grafu BFS."""

from __future__ import annotations

from forensics.core.graph import build_trace_graph
from forensics.core.models import Transaction


class RecordingEtherscan:
    """Minimalny fake klienta Etherscan do sprawdzania parametrow wywolan."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int, str]] = []

    async def get_normal_transactions(
        self,
        address: str,
        start_block: int = 0,
        end_block: int = 99_999_999,
        offset: int = 50,
        sort: str = "desc",
    ) -> list[Transaction]:
        self.calls.append(("normal", start_block, end_block, sort))
        return []

    async def get_token_transfers(
        self,
        address: str,
        start_block: int = 0,
        end_block: int = 99_999_999,
        offset: int = 50,
        sort: str = "desc",
    ) -> list[Transaction]:
        self.calls.append(("token", start_block, end_block, sort))
        return []


async def test_incident_window_fetches_oldest_transactions_first() -> None:
    """Okno incydentu musi brac poczatek okna, nie najnowsze tx z konca."""
    etherscan = RecordingEtherscan()

    await build_trace_graph(
        etherscan,  # type: ignore[arg-type]
        root_address="0x" + "a" * 40,
        hops=1,
        start_block=100,
        end_block=200,
    )

    assert etherscan.calls == [
        ("normal", 100, 200, "asc"),
        ("token", 100, 200, "asc"),
    ]
