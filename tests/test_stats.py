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


def test_by_category_groups_expenses(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    wallet = client.post(
        "/wallets", json={"name": "Cash"}, headers=auth_headers
    ).json()
    cats = client.get("/categories", headers=auth_headers).json()
    food = next(c for c in cats if c["default_key"] == "food")
    transport = next(c for c in cats if c["default_key"] == "transport")

    for amount, cat in ((50000, food), (30000, food), (20000, transport)):
        client.post(
            "/transactions",
            json={
                "wallet_rid": wallet["rid"],
                "type": "expense",
                "amount": amount,
                "category_rid": cat["rid"],
            },
            headers=auth_headers,
        )
    # An uncategorized expense folds into its own bucket.
    client.post(
        "/transactions",
        json={"wallet_rid": wallet["rid"], "type": "expense", "amount": 10000},
        headers=auth_headers,
    )

    resp = client.get("/stats/by-category?kind=expense", headers=auth_headers)
    assert resp.status_code == 200
    slices = resp.json()
    # Sorted by amount desc: food (80k), transport (20k), uncategorized (10k).
    assert [s["amount"] for s in slices] == [80000, 20000, 10000]
    assert slices[0]["default_key"] == "food"
    assert slices[2]["category_rid"] is None
    assert slices[2]["default_key"] == "uncategorized"


def test_by_category_filters_by_kind(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    wallet = client.post(
        "/wallets", json={"name": "Cash"}, headers=auth_headers
    ).json()
    cats = client.get("/categories", headers=auth_headers).json()
    salary = next(c for c in cats if c["default_key"] == "salary")
    client.post(
        "/transactions",
        json={
            "wallet_rid": wallet["rid"],
            "type": "income",
            "amount": 500000,
            "category_rid": salary["rid"],
        },
        headers=auth_headers,
    )

    expense = client.get(
        "/stats/by-category?kind=expense", headers=auth_headers
    ).json()
    assert expense == []  # the income transaction is excluded

    income = client.get(
        "/stats/by-category?kind=income", headers=auth_headers
    ).json()
    assert [s["amount"] for s in income] == [500000]
    assert income[0]["default_key"] == "salary"


def test_by_category_requires_auth(client: TestClient) -> None:
    assert client.get("/stats/by-category").status_code == 401
