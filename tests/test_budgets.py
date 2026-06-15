"""Per-category monthly budgets and current-month spending."""

from datetime import date

from fastapi.testclient import TestClient


def _category(client: TestClient, headers: dict[str, str], name: str = "Food") -> str:
    return client.post(
        "/categories",
        json={"name": name, "kind": "expense"},
        headers=headers,
    ).json()["rid"]


def _wallet(
    client: TestClient, headers: dict[str, str], visibility: str = "personal"
) -> str:
    return client.post(
        "/wallets",
        json={"name": "Cash", "visibility": visibility},
        headers=headers,
    ).json()["rid"]


def test_create_and_list_budget_with_spent(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # Personal scope (the default): personal category + personal wallet + budget.
    cat = _category(client, auth_headers)
    w = _wallet(client, auth_headers)
    # Two expenses in that category this month.
    today = date.today().isoformat()
    for amt in (30000, 20000):
        client.post(
            "/transactions",
            json={
                "wallet_rid": w,
                "type": "expense",
                "amount": amt,
                "category_rid": cat,
                "occurred_on": today,
            },
            headers=auth_headers,
        )
    created = client.post(
        "/budgets", json={"category_rid": cat, "amount": 100000}, headers=auth_headers
    )
    assert created.status_code == 201

    budgets = client.get("/budgets", headers=auth_headers).json()
    assert len(budgets) == 1
    assert budgets[0]["amount"] == 100000
    assert budgets[0]["spent"] == 50000
    assert budgets[0]["category"]["rid"] == cat


def test_duplicate_budget_is_409(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    cat = _category(client, auth_headers)
    assert (
        client.post(
            "/budgets", json={"category_rid": cat, "amount": 100}, headers=auth_headers
        ).status_code
        == 201
    )
    dup = client.post(
        "/budgets", json={"category_rid": cat, "amount": 200}, headers=auth_headers
    )
    assert dup.status_code == 409


def test_update_and_delete_budget(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    cat = _category(client, auth_headers)
    rid = client.post(
        "/budgets", json={"category_rid": cat, "amount": 100}, headers=auth_headers
    ).json()["rid"]

    upd = client.patch(f"/budgets/{rid}", json={"amount": 500}, headers=auth_headers)
    assert upd.status_code == 200
    assert upd.json()["amount"] == 500

    assert client.delete(f"/budgets/{rid}", headers=auth_headers).status_code == 204
    assert client.get("/budgets", headers=auth_headers).json() == []


def test_budget_for_unknown_category_is_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/budgets", json={"category_rid": "nope", "amount": 100}, headers=auth_headers
    )
    assert resp.status_code == 404


def test_family_budget_scope(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # A family category + family wallet + family-scope budget tracks family spend.
    cat = client.post(
        "/categories?scope=family",
        json={"name": "Chợ", "kind": "expense"},
        headers=auth_headers,
    ).json()["rid"]
    w = _wallet(client, auth_headers, visibility="family")
    today = date.today().isoformat()
    client.post(
        "/transactions",
        json={
            "wallet_rid": w,
            "type": "expense",
            "amount": 70000,
            "category_rid": cat,
            "occurred_on": today,
        },
        headers=auth_headers,
    )
    created = client.post(
        "/budgets?scope=family",
        json={"category_rid": cat, "amount": 200000},
        headers=auth_headers,
    )
    assert created.status_code == 201
    assert created.json()["spent"] == 70000
    # The family budget is not in the personal list, and vice-versa.
    assert client.get("/budgets?scope=personal", headers=auth_headers).json() == []
    fam = client.get("/budgets?scope=family", headers=auth_headers).json()
    assert len(fam) == 1 and fam[0]["spent"] == 70000


def test_personal_budget_without_family(client: TestClient) -> None:
    # A family-less account can create personal categories + budgets.
    reg = client.post(
        "/auth/register",
        json={"email": "solo3@example.com", "password": "s3cret-pass",
              "display_name": "Solo"},
    )
    assert reg.status_code == 201
    login = client.post(
        "/auth/login", data={"username": "solo3@example.com", "password": "s3cret-pass"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    # Personal categories were seeded at registration.
    assert len(client.get("/categories", headers=headers).json()) > 0
    cat = _category(client, headers, name="Cà phê")
    resp = client.post(
        "/budgets", json={"category_rid": cat, "amount": 50000}, headers=headers
    )
    assert resp.status_code == 201
    # A shared (family) budget needs a family.
    assert (
        client.post(
            "/budgets?scope=family",
            json={"category_rid": cat, "amount": 50000},
            headers=headers,
        ).status_code
        == 400
    )
