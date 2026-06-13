"""Categories: seeded defaults, CRUD, and transaction integration."""

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


def test_new_family_has_default_categories(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    cats = client.get("/categories", headers=auth_headers).json()
    assert len(cats) == 12
    keys = {c["default_key"] for c in cats}
    assert "food" in keys and "salary" in keys
    assert all(c["default_key"] is not None for c in cats)


def test_create_custom_category(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/categories",
        json={"name": "Pets", "kind": "expense", "icon": "🐶"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Pets"
    assert body["default_key"] is None


def test_renaming_default_clears_default_key(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    food = next(
        c for c in client.get("/categories", headers=auth_headers).json()
        if c["default_key"] == "food"
    )
    patched = client.patch(
        f"/categories/{food['rid']}", json={"name": "Groceries"}, headers=auth_headers
    ).json()
    assert patched["name"] == "Groceries"
    assert patched["default_key"] is None


def test_archive_hides_from_default_list(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    cat = client.post(
        "/categories", json={"name": "Temp", "kind": "expense"}, headers=auth_headers
    ).json()
    client.patch(
        f"/categories/{cat['rid']}", json={"is_archived": True}, headers=auth_headers
    )
    visible = [c["rid"] for c in client.get("/categories", headers=auth_headers).json()]
    assert cat["rid"] not in visible
    all_cats = client.get(
        "/categories?include_archived=true", headers=auth_headers
    ).json()
    assert cat["rid"] in [c["rid"] for c in all_cats]


def test_transaction_with_category(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    wallet = client.post("/wallets", json={"name": "Cash"}, headers=auth_headers).json()
    food = next(
        c for c in client.get("/categories", headers=auth_headers).json()
        if c["default_key"] == "food"
    )
    txn = client.post(
        "/transactions",
        json={
            "wallet_rid": wallet["rid"],
            "type": "expense",
            "amount": 50000,
            "category_rid": food["rid"],
        },
        headers=auth_headers,
    )
    assert txn.status_code == 201
    assert txn.json()["category"]["default_key"] == "food"


def test_transaction_with_unknown_category_is_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    wallet = client.post("/wallets", json={"name": "Cash"}, headers=auth_headers).json()
    resp = client.post(
        "/transactions",
        json={
            "wallet_rid": wallet["rid"],
            "type": "expense",
            "amount": 1000,
            "category_rid": "nope",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_deleting_category_uncategorizes_transactions(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    wallet = client.post("/wallets", json={"name": "Cash"}, headers=auth_headers).json()
    cat = client.post(
        "/categories", json={"name": "Pets", "kind": "expense"}, headers=auth_headers
    ).json()
    client.post(
        "/transactions",
        json={
            "wallet_rid": wallet["rid"],
            "type": "expense",
            "amount": 1000,
            "category_rid": cat["rid"],
        },
        headers=auth_headers,
    )
    assert client.delete(f"/categories/{cat['rid']}", headers=auth_headers).status_code == 204
    txns = client.get("/transactions", headers=auth_headers).json()
    assert txns[0]["category"] is None


def test_cannot_use_other_familys_category(client: TestClient) -> None:
    a = _register(client, "a@example.com", "Family A")
    b = _register(client, "b@example.com", "Family B")
    a_cat = client.get("/categories", headers=a).json()[0]["rid"]
    wallet_b = client.post("/wallets", json={"name": "B"}, headers=b).json()["rid"]
    resp = client.post(
        "/transactions",
        json={"wallet_rid": wallet_b, "type": "expense", "amount": 1000, "category_rid": a_cat},
        headers=b,
    )
    assert resp.status_code == 404
