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
