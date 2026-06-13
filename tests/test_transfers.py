"""Wallet-to-wallet transfers: balances move, income/expense untouched."""

from fastapi.testclient import TestClient


def _wallet(client: TestClient, headers: dict[str, str], name: str) -> str:
    return client.post("/wallets", json={"name": name}, headers=headers).json()["rid"]


def _balances(client: TestClient, headers: dict[str, str]) -> dict[str, int]:
    return {
        w["name"]: w["balance"]
        for w in client.get("/wallets", headers=headers).json()
    }


def _seed_income(
    client: TestClient, headers: dict[str, str], wallet_rid: str, amount: int
) -> None:
    client.post(
        "/transactions",
        json={"wallet_rid": wallet_rid, "type": "income", "amount": amount},
        headers=headers,
    )


def test_transfer_moves_balance_without_touching_totals(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    a = _wallet(client, auth_headers, "A")
    b = _wallet(client, auth_headers, "B")
    _seed_income(client, auth_headers, a, 100000)

    resp = client.post(
        "/transfers",
        json={"from_wallet_rid": a, "to_wallet_rid": b, "amount": 30000},
        headers=auth_headers,
    )
    assert resp.status_code == 201

    balances = _balances(client, auth_headers)
    assert balances["A"] == 70000
    assert balances["B"] == 30000

    # Transfers must not inflate income/expense totals.
    summary = client.get("/dashboard/summary", headers=auth_headers).json()
    assert summary["total_income"] == 100000
    assert summary["total_expense"] == 0
    assert summary["net_balance"] == 100000


def test_delete_transfer_reverts_balances(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    a = _wallet(client, auth_headers, "A")
    b = _wallet(client, auth_headers, "B")
    _seed_income(client, auth_headers, a, 50000)
    group = client.post(
        "/transfers",
        json={"from_wallet_rid": a, "to_wallet_rid": b, "amount": 20000},
        headers=auth_headers,
    ).json()["group_rid"]

    assert client.delete(f"/transfers/{group}", headers=auth_headers).status_code == 204
    balances = _balances(client, auth_headers)
    assert balances["A"] == 50000
    assert balances["B"] == 0


def test_transfer_to_same_wallet_is_400(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    a = _wallet(client, auth_headers, "A")
    resp = client.post(
        "/transfers",
        json={"from_wallet_rid": a, "to_wallet_rid": a, "amount": 1000},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_transfer_unknown_wallet_is_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    a = _wallet(client, auth_headers, "A")
    resp = client.post(
        "/transfers",
        json={"from_wallet_rid": a, "to_wallet_rid": "nope", "amount": 1000},
        headers=auth_headers,
    )
    assert resp.status_code == 404
