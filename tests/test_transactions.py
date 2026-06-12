"""Transaction creation, balance derivation, and the dashboard total."""

from fastapi.testclient import TestClient


def _make_wallet(client: TestClient, headers: dict[str, str], name: str = "Cash") -> str:
    resp = client.post("/wallets", json={"name": name}, headers=headers)
    return resp.json()["rid"]


def test_income_and_expense_derive_balance(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    wallet_rid = _make_wallet(client, auth_headers)

    client.post(
        "/transactions",
        json={"wallet_rid": wallet_rid, "type": "income", "amount": 1_000_000},
        headers=auth_headers,
    )
    client.post(
        "/transactions",
        json={"wallet_rid": wallet_rid, "type": "expense", "amount": 250_000},
        headers=auth_headers,
    )

    wallet = client.get(f"/wallets/{wallet_rid}", headers=auth_headers).json()
    assert wallet["balance"] == 750_000


def test_amount_must_be_positive(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    wallet_rid = _make_wallet(client, auth_headers)
    resp = client.post(
        "/transactions",
        json={"wallet_rid": wallet_rid, "type": "expense", "amount": 0},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_transaction_on_unknown_wallet_is_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/transactions",
        json={"wallet_rid": "NOPE", "type": "income", "amount": 100},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_dashboard_summary_totals(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    cash = _make_wallet(client, auth_headers, "Cash")
    bank = _make_wallet(client, auth_headers, "Bank")

    client.post(
        "/transactions",
        json={"wallet_rid": cash, "type": "income", "amount": 500_000},
        headers=auth_headers,
    )
    client.post(
        "/transactions",
        json={"wallet_rid": bank, "type": "income", "amount": 2_000_000},
        headers=auth_headers,
    )
    client.post(
        "/transactions",
        json={"wallet_rid": cash, "type": "expense", "amount": 300_000},
        headers=auth_headers,
    )

    summary = client.get("/dashboard/summary", headers=auth_headers).json()
    assert summary["total_income"] == 2_500_000
    assert summary["total_expense"] == 300_000
    assert summary["net_balance"] == 2_200_000
    assert summary["wallet_count"] == 2
    balances = {w["name"]: w["balance"] for w in summary["wallets"]}
    assert balances == {"Cash": 200_000, "Bank": 2_000_000}
