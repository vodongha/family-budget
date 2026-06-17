"""A transfer crossing the personal↔family boundary counts as income/expense for
each scope (but stays neutral in the combined 'all' view and for internal
transfers). See the money rules in CLAUDE.md."""

from fastapi.testclient import TestClient


def _wallet(client: TestClient, headers: dict[str, str], name: str, vis: str) -> str:
    resp = client.post(
        "/wallets",
        json={"name": name, "visibility": vis},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["rid"]


def _summary(client: TestClient, headers: dict[str, str], scope: str) -> dict:
    return client.get(
        f"/dashboard/summary?scope={scope}", headers=headers
    ).json()


def test_personal_to_family_transfer_scopes(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    personal = _wallet(client, auth_headers, "My cash", "personal")
    family = _wallet(client, auth_headers, "Shared", "family")
    resp = client.post(
        "/transfers",
        json={
            "from_wallet_rid": personal,
            "to_wallet_rid": family,
            "amount": 100000,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text

    # Family scope: money came in from a member's private funds → income.
    fam = _summary(client, auth_headers, "family")
    assert fam["total_income"] == 100000
    assert fam["total_expense"] == 0
    assert fam["net_balance"] == 100000  # matches the family wallet balance

    # Personal scope: money left the private wallet → expense.
    per = _summary(client, auth_headers, "personal")
    assert per["total_expense"] == 100000
    assert per["total_income"] == 0

    # Combined: it only moved within the user's own holdings → neutral.
    allv = _summary(client, auth_headers, "all")
    assert allv["total_income"] == 0
    assert allv["total_expense"] == 0


def test_internal_family_transfer_is_neutral(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    f1 = _wallet(client, auth_headers, "Bank", "family")
    f2 = _wallet(client, auth_headers, "Wallet", "family")
    resp = client.post(
        "/transfers",
        json={"from_wallet_rid": f1, "to_wallet_rid": f2, "amount": 50000},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text

    # Both legs are inside the family scope → no income/expense effect.
    fam = _summary(client, auth_headers, "family")
    assert fam["total_income"] == 0
    assert fam["total_expense"] == 0


def test_boundary_transfer_in_monthly_stats(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    personal = _wallet(client, auth_headers, "Pocket", "personal")
    family = _wallet(client, auth_headers, "Family", "family")
    client.post(
        "/transfers",
        json={
            "from_wallet_rid": personal,
            "to_wallet_rid": family,
            "amount": 70000,
        },
        headers=auth_headers,
    )
    monthly = client.get(
        "/stats/monthly?months=1&scope=family", headers=auth_headers
    ).json()
    assert monthly[-1]["income"] == 70000
