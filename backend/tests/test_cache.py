"""Testy dyskowego cache (forensics.cache).

Kluczowe gwarancje:
- sekrety (apikey) nigdy nie trafiaja do klucza ani na dysk,
- ten sam klucz niezaleznie od apikey,
- hit/miss zliczane per provider,
- tryb refresh pomija cache,
- clear() czysci, status() liczy.

Izolacja: kazdy test dostaje wlasny katalog cache przez env FORENSICS_CACHE_DIR.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forensics import cache


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORENSICS_CACHE_DIR", str(tmp_path))
    cache.begin_request(refresh=False)  # czyste staty na start kazdego testu


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    payload = {"status": "1", "result": [{"hash": "0xabc"}]}
    cache.write("etherscan", "txlist", {"address": "0xAbC", "startblock": 1}, payload, 200)

    env = cache.read("etherscan", "txlist", {"address": "0xAbC", "startblock": 1})

    assert env is not None
    assert env["payload"] == payload
    assert env["provider"] == "etherscan"
    assert env["action"] == "txlist"
    assert env["status_code"] == 200
    assert env["cache_version"] == cache.CACHE_VERSION
    assert "fetched_at" in env


def test_secret_never_in_key_or_file(tmp_path: Path) -> None:
    params = {"address": "0xabc", "apikey": "SUPER_SECRET_123", "module": "account"}
    cache.write("etherscan", "txlist", params, {"status": "1"}, 200)

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "SUPER_SECRET_123" not in content
    assert "apikey" not in content

    env = cache.read("etherscan", "txlist", params)
    assert env is not None
    assert "apikey" not in env["params"]
    assert env["params"]["address"] == "0xabc"


def test_same_key_regardless_of_apikey(tmp_path: Path) -> None:
    cache.write("etherscan", "txlist", {"address": "0xabc", "apikey": "KEY1"}, {"x": 1}, 200)
    cache.write("etherscan", "txlist", {"address": "0xabc", "apikey": "KEY2"}, {"x": 2}, 200)

    # apikey nie wplywa na klucz -> jeden plik, drugi zapis nadpisal pierwszy
    assert len(list(tmp_path.glob("*.json"))) == 1
    env = cache.read("etherscan", "txlist", {"address": "0xabc", "apikey": "KEY1"})
    assert env is not None
    assert env["payload"] == {"x": 2}


def test_hit_miss_stats_per_provider() -> None:
    cache.begin_request(refresh=False)
    assert cache.read("arkham", "address_intelligence", {"address": "0x1"}) is None  # miss
    cache.write("arkham", "address_intelligence", {"address": "0x1"}, {"k": 1}, 200)
    assert cache.read("arkham", "address_intelligence", {"address": "0x1"}) is not None  # hit

    assert cache.current_stats()["arkham"] == {"hit": 1, "miss": 1}


def test_refresh_mode_bypasses_cache() -> None:
    cache.write("arkham", "address_intelligence", {"address": "0x1"}, {"k": 1}, 200)

    cache.begin_request(refresh=True)
    assert cache.read("arkham", "address_intelligence", {"address": "0x1"}) is None  # mimo pliku
    assert cache.current_stats()["arkham"] == {"hit": 0, "miss": 1}


def test_clear_and_status(tmp_path: Path) -> None:
    cache.write("etherscan", "txlist", {"a": 1}, {"x": 1}, 200)
    cache.write("arkham", "address_intelligence", {"address": "0x1"}, {"y": 1}, 200)

    st = cache.status()
    assert st["total_files"] == 2
    assert st["providers"] == {"etherscan": 1, "arkham": 1}
    assert st["cache_version"] == cache.CACHE_VERSION

    assert cache.clear() == 2
    assert cache.status()["total_files"] == 0
