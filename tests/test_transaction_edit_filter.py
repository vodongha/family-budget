"""Editing, deleting and filtering transactions."""

from fastapi.testclient import TestClient


def _wallet(client: TestClient, headers: dict[str, str], name: str = "Cash") -> str:
    return client.post("/wallets", json={"name": name}, headers=headers).json()["rid"]


def _txn(
    client: TestClient,
    headers: dict[str, str],
    wallet_rid: str,
    *,
    type_: str = "expense",
    amount: int = 1000,
    occurred_on: str | None = None,
) -> dict:
    body = {"wallet_rid": wallet_rid, "type": type_, "amount": amount}
    if occurred_on is not None:
        body["occurred_on"] = occurred_on
    return client.post("/transactions", json=body, headers=headers).json()


def test_update_transaction(client: TestClient, auth_headers: dict[str, str]) -> None:
    w = _wallet(client, auth_headers)
    rid = _txn(client, auth_headers, w, amount=1000)["rid"]
    resp = client.patch(
        f"/transactions/{rid}",
        json={"wallet_rid": w, "type": "income", "amount": 2500, "note": "fixed"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "income"
    assert body["amount"] == 2500
    assert body["note"] == "fixed"


def test_delete_transaction(client: TestClient, auth_headers: dict[str, str]) -> None:
    w = _wallet(client, auth_headers)
    rid = _txn(client, auth_headers, w)["rid"]
    assert client.delete(f"/transactions/{rid}", headers=auth_headers).status_code == 204
    # Gone from the list.
    listed = client.get("/transactions", headers=auth_headers).json()
    assert all(t["rid"] != rid for t in listed)


def test_update_unknown_is_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    w = _wallet(client, auth_headers)
    resp = client.patch(
        "/transactions/nope",
        json={"wallet_rid": w, "type": "expense", "amount": 100},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_filter_by_type(client: TestClient, auth_headers: dict[str, str]) -> None:
    w = _wallet(client, auth_headers)
    _txn(client, auth_headers, w, type_="expense", amount=100)
    _txn(client, auth_headers, w, type_="income", amount=200)
    income = client.get("/transactions?type=income", headers=auth_headers).json()
    assert [t["type"] for t in income] == ["income"]


def test_filter_by_date_range(client: TestClient, auth_headers: dict[str, str]) -> None:
    w = _wallet(client, auth_headers)
    _txn(client, auth_headers, w, amount=1, occurred_on="2026-01-15")
    _txn(client, auth_headers, w, amount=2, occurred_on="2026-03-20")
    _txn(client, auth_headers, w, amount=3, occurred_on="2026-06-10")
    resp = client.get(
        "/transactions?date_from=2026-03-01&date_to=2026-03-31", headers=auth_headers
    )
    amounts = sorted(t["amount"] for t in resp.json())
    assert amounts == [2]


def test_cannot_edit_other_members_personal_txn(client: TestClient) -> None:
    # Owner makes a personal wallet + txn; another member must not see/edit it.
    client.post(
        "/auth/register",
        json={
            "email": "a@example.com",
            "password": "s3cret-pass",
            "display_name": "A",
            "family_name": "Fam",
        },
    )
    login = client.post(
        "/auth/login", data={"username": "a@example.com", "password": "s3cret-pass"}
    )
    owner_h = {"Authorization": f"Bearer {login.json()['access_token']}"}
    pw = client.post(
        "/wallets",
        json={"name": "Secret", "visibility": "personal"},
        headers=owner_h,
    ).json()["rid"]
    rid = _txn(client, owner_h, pw)["rid"]

    # Invite a member.
    token = client.post(
        "/invitations", json={"email": "b@example.com"}, headers=owner_h
    ).json()["token"]
    accept = client.post(
        "/invitations/accept",
        json={"token": token, "password": "p", "display_name": "B"},
    )
    member_h = {"Authorization": f"Bearer {accept.json()['access_token']}"}

    assert client.delete(f"/transactions/{rid}", headers=member_h).status_code == 404
