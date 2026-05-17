from fastapi.testclient import TestClient

from forensics.api import app


def test_root_health_check() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
