"""Monthly statistics aggregation."""

from fastapi.testclient import TestClient


def test_monthly_returns_window_with_current_month_totals(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    wallet = client.post(
        "/wallets", json={"name": "Cash"}, headers=auth_headers
    ).json()
    client.post(
        "/transactions",
        json={"wallet_rid": wallet["rid"], "type": "income", "amount": 300000},
        headers=auth_headers,
    )
    client.post(
        "/transactions",
        json={"wallet_rid": wallet["rid"], "type": "expense", "amount": 50000},
        headers=auth_headers,
    )

    resp = client.get("/stats/monthly?months=3", headers=auth_headers)
    assert resp.status_code == 200
    points = resp.json()
    assert len(points) == 3  # oldest -> newest

    # Today's transactions land in the last bucket.
    current = points[-1]
    assert current["income"] == 300000
    assert current["expense"] == 50000


def test_monthly_requires_auth(client: TestClient) -> None:
    assert client.get("/stats/monthly").status_code == 401


def test_monthly_clamps_months(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # months above the cap is clamped (no error), below 1 becomes 1.
    assert len(client.get("/stats/monthly?months=999", headers=auth_headers).json()) == 24
    assert len(client.get("/stats/monthly?months=0", headers=auth_headers).json()) == 1
