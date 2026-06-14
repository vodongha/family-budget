"""Health endpoint. Against SQLite the `SELECT 1 FROM dual` won't resolve, so we
assert the endpoint reports degraded gracefully rather than crashing. The real
ADB connectivity check is exercised live via `curl /health` after the wallet is
mounted (see README).
"""

from fastapi.testclient import TestClient


def test_health_endpoint_responds(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "database" in body
    assert "status" in body


def test_meta(client: TestClient) -> None:
    resp = client.get("/meta")
    assert resp.status_code == 200
    assert resp.json()["app"] == "family-budget"
