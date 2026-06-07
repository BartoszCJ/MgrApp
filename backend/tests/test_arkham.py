"""Testy cache'a klienta Arkham (oparty o dyskowy forensics.cache).

Cache ma chronic free tier: ten sam adres pytany jest tylko raz.
Sprawdzamy to liczac realne zapytania HTTP przez httpx.MockTransport.

Izolacja: kazdy test ma wlasny katalog cache (FORENSICS_CACHE_DIR -> tmp_path).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from forensics.clients.arkham import ArkhamClient


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORENSICS_CACHE_DIR", str(tmp_path))


async def _make_client(handler: Callable[[httpx.Request], httpx.Response]) -> ArkhamClient:
    client = ArkhamClient(api_key="test-key")
    await client.client.aclose()  # zamykamy auto-utworzony transport
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


async def test_cache_serves_repeated_lookup_without_second_request() -> None:
    """Ten sam adres (rozny case) = 1 zapytanie HTTP mimo 3 lookupow."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={"arkhamEntity": {"name": "Binance", "type": "cex"}})

    client = await _make_client(handler)
    addr = "0x" + "A" * 40

    first = await client.get_address_intelligence(addr)
    second = await client.get_address_intelligence(addr)
    third = await client.get_address_intelligence(addr.lower())

    assert first is not None
    assert first.entity == "Binance"
    assert first.category == "cex"
    assert second == first
    assert third == first
    assert len(calls) == 1  # tylko 1 realne zapytanie do Arkhama

    await client.close()


async def test_cache_remembers_unknown_address() -> None:
    """404 (adres nieznany) tez jest cache'owany - nie pytamy drugi raz."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(404)

    client = await _make_client(handler)
    addr = "0x" + "b" * 40

    assert await client.get_address_intelligence(addr) is None
    assert await client.get_address_intelligence(addr) is None
    assert len(calls) == 1

    await client.close()


async def test_rate_limit_is_not_cached() -> None:
    """429 jest przejsciowy - nie wolno go cache'owac, retry musi dojsc do API."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"arkhamEntity": {"name": "Kraken", "type": "cex"}})

    client = await _make_client(handler)
    addr = "0x" + "c" * 40

    assert await client.get_address_intelligence(addr) is None  # 429
    result = await client.get_address_intelligence(addr)  # retry -> 200
    assert result is not None
    assert result.entity == "Kraken"
    assert len(calls) == 2  # 429 nie zostalo zapamietane

    await client.close()
