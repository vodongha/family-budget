"""Exchange-rate status + manual refresh endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.domains.rates.tasks as rates_tasks
from app.domains.rates.models import ExchangeRate


class _FakeResp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *a: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def test_get_rates_status(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    empty = client.get("/rates", headers=auth_headers).json()
    assert empty["base_currency"] == "VND"
    assert empty["updated_at"] is None
    assert empty["count"] == 0

    db_session.add(ExchangeRate(currency="USD", rate_to_base=25000.0))
    db_session.commit()
    seeded = client.get("/rates", headers=auth_headers).json()
    assert seeded["count"] == 1
    assert seeded["updated_at"] is not None


def test_get_rates_lists_stored_rates(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    db_session.add(ExchangeRate(currency="USD", rate_to_base=25000.0))
    db_session.add(ExchangeRate(currency="JPY", rate_to_base=165.0))
    db_session.commit()
    body = client.get("/rates", headers=auth_headers).json()
    by_code = {r["currency"]: r["rate_to_base"] for r in body["rates"]}
    assert by_code["USD"] == 25000.0
    assert by_code["JPY"] == 165.0


def test_get_rates_requires_auth(client: TestClient) -> None:
    assert client.get("/rates").status_code == 401


def test_refresh_rates_pulls_and_reports(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rates_tasks.urllib.request,
        "urlopen",
        lambda *a, **k: _FakeResp(b'{"rates": {"USD": 0.00004, "VND": 1}}'),
    )
    resp = client.post("/rates/refresh", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] >= 1
    assert body["updated_at"] is not None


def test_refresh_rates_503_when_source_down(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*a: object, **k: object) -> None:
        raise OSError("network down")

    monkeypatch.setattr(rates_tasks.urllib.request, "urlopen", _boom)
    assert client.post("/rates/refresh", headers=auth_headers).status_code == 503
