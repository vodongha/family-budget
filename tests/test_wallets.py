"""Wallet creation, listing, and tenant scoping."""

from fastapi.testclient import TestClient


def test_create_wallet_starts_at_zero_balance(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post("/wallets", json={"name": "Cash"}, headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Cash"
    assert body["balance"] == 0
    assert len(body["rid"]) == 26


def test_list_wallets_returns_created(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post("/wallets", json={"name": "Cash"}, headers=auth_headers)
    client.post("/wallets", json={"name": "Bank"}, headers=auth_headers)
    resp = client.get("/wallets", headers=auth_headers)
    assert resp.status_code == 200
    names = {w["name"] for w in resp.json()}
    assert names == {"Cash", "Bank"}


def test_wallets_require_auth(client: TestClient) -> None:
    assert client.get("/wallets").status_code == 401


def test_get_unknown_wallet_is_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert client.get("/wallets/NOPE", headers=auth_headers).status_code == 404
