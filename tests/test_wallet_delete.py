"""Deleting a wallet removes it and its transactions (owner-only)."""

from fastapi.testclient import TestClient


def _register(client: TestClient, email: str, family: str = "Fam") -> dict[str, str]:
    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "s3cret-pass",
            "display_name": email.split("@")[0],
            "family_name": family,
        },
    )
    login = client.post(
        "/auth/login", data={"username": email, "password": "s3cret-pass"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _invite_member(client: TestClient, owner: dict[str, str], email: str) -> dict[str, str]:
    token = client.post(
        "/invitations", json={"email": email}, headers=owner
    ).json()["token"]
    accept = client.post(
        "/invitations/accept",
        json={"token": token, "password": "p", "display_name": email.split("@")[0]},
    )
    return {"Authorization": f"Bearer {accept.json()['access_token']}"}


def _wallet_with_txn(client: TestClient, headers: dict[str, str]) -> str:
    rid = client.post("/wallets", json={"name": "Cash"}, headers=headers).json()["rid"]
    client.post(
        "/transactions",
        json={"wallet_rid": rid, "type": "expense", "amount": 1000},
        headers=headers,
    )
    return rid


def test_list_includes_txn_count(client: TestClient, auth_headers: dict[str, str]) -> None:
    rid = _wallet_with_txn(client, auth_headers)
    wallets = client.get("/wallets", headers=auth_headers).json()
    wallet = next(w for w in wallets if w["rid"] == rid)
    assert wallet["txn_count"] == 1


def test_owner_deletes_wallet_and_transactions(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    rid = _wallet_with_txn(client, auth_headers)

    resp = client.delete(f"/wallets/{rid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["deleted_transactions"] == 1

    # Wallet is gone, and its transactions with it.
    assert client.get(f"/wallets/{rid}", headers=auth_headers).status_code == 404
    txns = client.get("/transactions", headers=auth_headers).json()
    assert txns == []


def test_member_cannot_delete_wallet(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    rid = client.post("/wallets", json={"name": "Cash"}, headers=auth_headers).json()["rid"]
    member = _invite_member(client, auth_headers, "mom@example.com")
    assert client.delete(f"/wallets/{rid}", headers=member).status_code == 403


def test_cannot_delete_other_familys_wallet(client: TestClient) -> None:
    a = _register(client, "a@example.com", "Family A")
    b = _register(client, "b@example.com", "Family B")
    rid = client.post("/wallets", json={"name": "A-Cash"}, headers=a).json()["rid"]
    assert client.delete(f"/wallets/{rid}", headers=b).status_code == 404
