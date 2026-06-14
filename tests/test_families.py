"""Family members listing and ownership transfer (single-owner model)."""

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


def _register_no_family(client: TestClient, email: str) -> dict[str, str]:
    """Register without a family (the decoupled flow), then sign in."""
    resp = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "s3cret-pass",
            "display_name": email.split("@")[0],
        },
    )
    assert resp.status_code == 201
    login = client.post(
        "/auth/login", data={"username": email, "password": "s3cret-pass"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_register_without_family_name_has_no_family(client: TestClient) -> None:
    headers = _register_no_family(client, "solo@example.com")
    me = client.get("/auth/me", headers=headers).json()
    assert me["family_id"] is None
    assert me["has_family"] is False


def test_create_family_makes_owner_and_seeds_categories(client: TestClient) -> None:
    headers = _register_no_family(client, "solo@example.com")
    resp = client.post("/families", json={"name": "Solo Home"}, headers=headers)
    assert resp.status_code == 201
    new_token = resp.json()["access_token"]
    new_headers = {"Authorization": f"Bearer {new_token}"}

    me = client.get("/auth/me", headers=new_headers).json()
    assert me["has_family"] is True
    assert me["role"] == "owner"
    # Default categories were seeded for the new family.
    assert len(client.get("/categories", headers=new_headers).json()) > 0


def test_create_family_when_already_in_one_is_409(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # auth_headers already owns "Vo Family".
    resp = client.post("/families", json={"name": "Another"}, headers=auth_headers)
    assert resp.status_code == 409


def test_owner_renames_family(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.patch("/families", json={"name": "Nhà Võ"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Nhà Võ"


def test_member_cannot_rename_family(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    member = _invite_member(client, auth_headers, "mom@example.com")
    resp = client.patch("/families", json={"name": "X"}, headers=member)
    assert resp.status_code == 403


def test_sole_owner_deletes_family_keeps_personal(client: TestClient) -> None:
    headers = _register(client, "solo2@example.com")
    client.post(
        "/wallets",
        json={"name": "Riêng", "visibility": "personal"},
        headers=headers,
    )
    resp = client.delete("/families", headers=headers)
    assert resp.status_code == 200
    new = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    assert client.get("/auth/me", headers=new).json()["has_family"] is False
    personal = client.get("/wallets?scope=personal", headers=new).json()
    assert [w["name"] for w in personal] == ["Riêng"]


def test_owner_cannot_delete_family_with_members(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    _invite_member(client, auth_headers, "mom@example.com")
    assert client.delete("/families", headers=auth_headers).status_code == 409


def test_member_leaves_family(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    member = _invite_member(client, auth_headers, "mom@example.com")
    resp = client.post("/families/leave", headers=member)
    assert resp.status_code == 200
    new = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    assert client.get("/auth/me", headers=new).json()["has_family"] is False
    # The owner still has the family.
    assert client.get("/auth/me", headers=auth_headers).json()["has_family"] is True


def test_owner_with_members_cannot_leave(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    _invite_member(client, auth_headers, "mom@example.com")
    assert client.post("/families/leave", headers=auth_headers).status_code == 409


def test_owner_removes_member(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    member = _invite_member(client, auth_headers, "mom@example.com")
    member_rid = client.get("/auth/me", headers=member).json()["rid"]
    resp = client.delete(f"/families/members/{member_rid}", headers=auth_headers)
    assert resp.status_code == 204
    assert client.get("/auth/me", headers=member).json()["has_family"] is False


def test_member_cannot_remove_others(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    member = _invite_member(client, auth_headers, "mom@example.com")
    owner_rid = client.get("/auth/me", headers=auth_headers).json()["rid"]
    resp = client.delete(f"/families/members/{owner_rid}", headers=member)
    assert resp.status_code == 403


def test_owner_cannot_remove_self(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    owner_rid = client.get("/auth/me", headers=auth_headers).json()["rid"]
    resp = client.delete(f"/families/members/{owner_rid}", headers=auth_headers)
    assert resp.status_code == 400


def test_personal_works_without_family(client: TestClient) -> None:
    headers = _register_no_family(client, "solo@example.com")
    # Personal space works with no family: empty wallet list, and a personal
    # wallet can be created and used.
    assert client.get("/wallets", headers=headers).status_code == 200
    assert client.get("/wallets", headers=headers).json() == []
    created = client.post(
        "/wallets",
        json={"name": "Ví của tôi", "visibility": "personal"},
        headers=headers,
    )
    assert created.status_code == 201
    wallets = client.get("/wallets?scope=personal", headers=headers).json()
    assert [w["name"] for w in wallets] == ["Ví của tôi"]
    # A shared (family) wallet still needs a family.
    blocked = client.post(
        "/wallets",
        json={"name": "Chung", "visibility": "family"},
        headers=headers,
    )
    assert blocked.status_code == 400
    # Dashboard + a personal transaction work without a family too.
    assert client.get("/dashboard/summary", headers=headers).status_code == 200
    rid = created.json()["rid"]
    txn = client.post(
        "/transactions",
        json={"wallet_rid": rid, "type": "income", "amount": 5000},
        headers=headers,
    )
    assert txn.status_code == 201
    assert client.get("/auth/me", headers=headers).json()["has_family"] is False


def test_list_members_shows_owner_and_member(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    _invite_member(client, auth_headers, "mom@example.com")
    members = client.get("/members", headers=auth_headers).json()
    by_email = {m["email"]: m for m in members}
    assert by_email["dad@example.com"]["role"] == "owner"
    assert by_email["mom@example.com"]["role"] == "member"


def test_owner_transfers_ownership(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    member_headers = _invite_member(client, auth_headers, "mom@example.com")
    member_rid = client.get("/auth/me", headers=member_headers).json()["rid"]

    resp = client.post(
        "/families/transfer-ownership",
        json={"target_rid": member_rid},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "owner"

    # Roles swapped.
    assert client.get("/auth/me", headers=auth_headers).json()["role"] == "member"
    assert client.get("/auth/me", headers=member_headers).json()["role"] == "owner"


def test_member_cannot_transfer(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    member_headers = _invite_member(client, auth_headers, "mom@example.com")
    owner_rid = client.get("/auth/me", headers=auth_headers).json()["rid"]
    resp = client.post(
        "/families/transfer-ownership",
        json={"target_rid": owner_rid},
        headers=member_headers,
    )
    assert resp.status_code == 403


def test_transfer_to_self_is_400(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    owner_rid = client.get("/auth/me", headers=auth_headers).json()["rid"]
    resp = client.post(
        "/families/transfer-ownership",
        json={"target_rid": owner_rid},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_transfer_to_outsider_is_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    outsider = _register(client, "outsider@example.com", "Other Fam")
    outsider_rid = client.get("/auth/me", headers=outsider).json()["rid"]
    resp = client.post(
        "/families/transfer-ownership",
        json={"target_rid": outsider_rid},
        headers=auth_headers,
    )
    assert resp.status_code == 404
