"""Personal vs family wallet privacy.

A personal wallet (and everything derived from it — balances, transactions,
dashboard totals, stats) is visible only to its owner, never to other members of
the same family, including the family owner.
"""

from fastapi.testclient import TestClient


def _invite_member(
    client: TestClient, owner_headers: dict[str, str], email: str
) -> dict[str, str]:
    token = client.post(
        "/invitations", json={"email": email}, headers=owner_headers
    ).json()["token"]
    accept = client.post(
        "/invitations/accept",
        json={"token": token, "password": "her-pass", "display_name": email.split("@")[0]},
    )
    return {"Authorization": f"Bearer {accept.json()['access_token']}"}


def _wallet(
    client: TestClient, headers: dict[str, str], name: str, visibility: str = "family"
) -> dict:
    return client.post(
        "/wallets",
        json={"name": name, "visibility": visibility},
        headers=headers,
    ).json()


def _expense(
    client: TestClient, headers: dict[str, str], wallet_rid: str, amount: int
) -> None:
    client.post(
        "/transactions",
        json={"wallet_rid": wallet_rid, "type": "expense", "amount": amount},
        headers=headers,
    )


def test_personal_wallet_hidden_from_other_members(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    mom = _invite_member(client, auth_headers, "mom@example.com")
    secret = _wallet(client, mom, "Secret", "personal")
    _expense(client, mom, secret["rid"], 70000)

    # The owner (dad) never sees mom's personal wallet.
    dad_wallets = client.get("/wallets", headers=auth_headers).json()
    assert all(w["rid"] != secret["rid"] for w in dad_wallets)
    assert client.get(f"/wallets/{secret['rid']}", headers=auth_headers).status_code == 404

    # Mom sees it herself, flagged personal.
    mom_wallets = {w["rid"]: w for w in client.get("/wallets", headers=mom).json()}
    assert mom_wallets[secret["rid"]]["visibility"] == "personal"
    assert mom_wallets[secret["rid"]]["balance"] == -70000


def test_personal_spending_excluded_from_other_dashboard(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    mom = _invite_member(client, auth_headers, "mom@example.com")
    secret = _wallet(client, mom, "Secret", "personal")
    _expense(client, mom, secret["rid"], 70000)

    # Dad's dashboard (default scope=all) does not include mom's private expense.
    dad = client.get("/dashboard/summary", headers=auth_headers).json()
    assert dad["total_expense"] == 0


def test_scope_separates_personal_and_family(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    family_wallet = _wallet(client, auth_headers, "Household", "family")
    _expense(client, auth_headers, family_wallet["rid"], 30000)
    secret = _wallet(client, auth_headers, "Mine", "personal")
    _expense(client, auth_headers, secret["rid"], 50000)

    family_only = client.get(
        "/dashboard/summary?scope=family", headers=auth_headers
    ).json()
    assert family_only["total_expense"] == 30000
    assert family_only["wallet_count"] == 1

    personal_only = client.get(
        "/dashboard/summary?scope=personal", headers=auth_headers
    ).json()
    assert personal_only["total_expense"] == 50000
    assert personal_only["wallet_count"] == 1

    everything = client.get(
        "/dashboard/summary?scope=all", headers=auth_headers
    ).json()
    assert everything["total_expense"] == 80000
    assert everything["wallet_count"] == 2


def test_member_cannot_write_to_others_personal_wallet(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    mom = _invite_member(client, auth_headers, "mom@example.com")
    secret = _wallet(client, mom, "Secret", "personal")

    # Dad can't add a transaction into mom's personal wallet.
    resp = client.post(
        "/transactions",
        json={"wallet_rid": secret["rid"], "type": "expense", "amount": 1000},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_transactions_list_respects_privacy(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    mom = _invite_member(client, auth_headers, "mom@example.com")
    secret = _wallet(client, mom, "Secret", "personal")
    _expense(client, mom, secret["rid"], 70000)

    dad_txns = client.get("/transactions", headers=auth_headers).json()
    assert dad_txns == []
    mom_txns = client.get("/transactions?scope=personal", headers=mom).json()
    assert [t["amount"] for t in mom_txns] == [70000]


def test_member_deletes_own_personal_wallet(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    mom = _invite_member(client, auth_headers, "mom@example.com")
    secret = _wallet(client, mom, "Secret", "personal")
    _expense(client, mom, secret["rid"], 70000)

    # A member (not the family owner) may delete their own personal wallet.
    resp = client.delete(f"/wallets/{secret['rid']}", headers=mom)
    assert resp.status_code == 200
    assert resp.json()["deleted_transactions"] == 1


def test_member_cannot_delete_family_wallet(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    mom = _invite_member(client, auth_headers, "mom@example.com")
    household = _wallet(client, auth_headers, "Household", "family")

    # A shared wallet can only be deleted by the family owner.
    resp = client.delete(f"/wallets/{household['rid']}", headers=mom)
    assert resp.status_code == 403


def test_by_category_excludes_others_personal(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    mom = _invite_member(client, auth_headers, "mom@example.com")
    secret = _wallet(client, mom, "Secret", "personal")
    cats = client.get("/categories", headers=mom).json()
    food = next(c for c in cats if c["default_key"] == "food")
    client.post(
        "/transactions",
        json={
            "wallet_rid": secret["rid"],
            "type": "expense",
            "amount": 40000,
            "category_rid": food["rid"],
        },
        headers=mom,
    )

    # Dad's by-category sees nothing of mom's private spending.
    dad = client.get("/stats/by-category?kind=expense", headers=auth_headers).json()
    assert dad == []
    # Mom's own personal-scope view does.
    mom_stats = client.get(
        "/stats/by-category?kind=expense&scope=personal", headers=mom
    ).json()
    assert [s["amount"] for s in mom_stats] == [40000]
