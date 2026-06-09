from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from forensics import api
from forensics.core.models import TraceRequest


def test_root_health_check() -> None:
    with TestClient(app=api.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


class _FakeEtherscan:
    """Minimalny fake - zero transakcji, zero sieci."""

    async def get_normal_transactions(self, *args: object, **kwargs: object) -> list:
        return []

    async def get_token_transfers(self, *args: object, **kwargs: object) -> list:
        return []


class _FakeArkham:
    def __init__(self) -> None:
        self.called = False

    async def get_many(self, addresses: list[str]) -> dict:
        self.called = True
        return {}


async def test_trace_skip_labels_skips_arkham(monkeypatch: pytest.MonkeyPatch) -> None:
    """skip_labels=true -> Arkham get_many NIE jest wolany (oszczedza free tier)."""
    fake_arkham = _FakeArkham()
    monkeypatch.setattr(api.app.state, "etherscan", _FakeEtherscan(), raising=False)
    monkeypatch.setattr(api.app.state, "arkham", fake_arkham, raising=False)

    result = await api.trace(TraceRequest(address="0x" + "a" * 40, hops=1, skip_labels=True))

    assert fake_arkham.called is False
    assert result.labels == []


async def test_trace_calls_arkham_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Domyslnie (skip_labels=false) Arkham jest wolany - pojedynczy trace chce etykiet."""
    fake_arkham = _FakeArkham()
    monkeypatch.setattr(api.app.state, "etherscan", _FakeEtherscan(), raising=False)
    monkeypatch.setattr(api.app.state, "arkham", fake_arkham, raising=False)

    await api.trace(TraceRequest(address="0x" + "a" * 40, hops=1))

    assert fake_arkham.called is True
