"""Invitations, roles, and cross-family isolation (the tenant boundary)."""

from fastapi.testclient import TestClient


def _register(client: TestClient, email: str, family: str) -> dict[str, str]:
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


def test_registering_user_is_owner(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    me = client.get("/auth/me", headers=auth_headers).json()
    assert me["role"] == "owner"


def test_owner_invites_and_invitee_joins_same_family(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # Owner creates a wallet, then invites a member.
    client.post("/wallets", json={"name": "Cash"}, headers=auth_headers)
    invite = client.post(
        "/invitations", json={"email": "mom@example.com"}, headers=auth_headers
    )
    assert invite.status_code == 201
    token = invite.json()["token"]
    assert invite.json()["role"] == "member"

    # Invitee accepts and is auto-logged-in.
    accept = client.post(
        "/invitations/accept",
        json={"token": token, "password": "her-pass", "display_name": "Mom"},
    )
    assert accept.status_code == 200
    member_headers = {"Authorization": f"Bearer {accept.json()['access_token']}"}

    me = client.get("/auth/me", headers=member_headers).json()
    assert me["role"] == "member"
    assert me["email"] == "mom@example.com"

    # Member sees the same family's wallet.
    wallets = client.get("/wallets", headers=member_headers).json()
    assert [w["name"] for w in wallets] == ["Cash"]


def test_member_cannot_invite(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    invite = client.post(
        "/invitations", json={"email": "mom@example.com"}, headers=auth_headers
    )
    accept = client.post(
        "/invitations/accept",
        json={
            "token": invite.json()["token"],
            "password": "her-pass",
            "display_name": "Mom",
        },
    )
    member_headers = {"Authorization": f"Bearer {accept.json()['access_token']}"}

    resp = client.post(
        "/invitations", json={"email": "kid@example.com"}, headers=member_headers
    )
    assert resp.status_code == 403


def test_accept_with_unknown_token_is_404(client: TestClient) -> None:
    resp = client.post(
        "/invitations/accept",
        json={"token": "nope", "password": "x", "display_name": "X"},
    )
    assert resp.status_code == 404


def test_cross_family_wallets_are_isolated(client: TestClient) -> None:
    headers_a = _register(client, "a@example.com", "Family A")
    headers_b = _register(client, "b@example.com", "Family B")

    created = client.post("/wallets", json={"name": "A-Cash"}, headers=headers_a).json()

    # B sees none of A's wallets...
    assert client.get("/wallets", headers=headers_b).json() == []
    # ...and cannot fetch A's wallet by rid.
    assert client.get(f"/wallets/{created['rid']}", headers=headers_b).status_code == 404


def test_owner_can_revoke_pending_invitation(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    invite = client.post(
        "/invitations", json={"email": "mom@example.com"}, headers=auth_headers
    ).json()
    revoke = client.delete(f"/invitations/{invite['rid']}", headers=auth_headers)
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "revoked"

    # A revoked token can no longer be accepted.
    accept = client.post(
        "/invitations/accept",
        json={"token": invite["token"], "password": "x", "display_name": "Mom"},
    )
    assert accept.status_code == 404


def test_invite_requires_email_or_phone(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post("/invitations", json={}, headers=auth_headers)
    assert resp.status_code == 422


def test_public_get_invitation_shows_family(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    invite = client.post(
        "/invitations", json={"phone": "0900000000"}, headers=auth_headers
    ).json()
    assert invite["phone"] == "0900000000"
    assert invite["email"] is None

    public = client.get(f"/invitations/{invite['token']}")
    assert public.status_code == 200
    assert public.json()["family_name"] == "Vo Family"
    assert public.json()["email"] is None


def test_phone_invite_accept_requires_then_uses_email(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    token = client.post(
        "/invitations", json={"phone": "0911111111"}, headers=auth_headers
    ).json()["token"]

    # Phone-only invite: accepting without an email is rejected.
    missing = client.post(
        "/invitations/accept",
        json={"token": token, "password": "her-pass", "display_name": "Mom"},
    )
    assert missing.status_code == 422

    # Supplying an email joins the family.
    ok = client.post(
        "/invitations/accept",
        json={
            "token": token,
            "password": "her-pass",
            "display_name": "Mom",
            "email": "mom2@example.com",
        },
    )
    assert ok.status_code == 200
    headers = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    me = client.get("/auth/me", headers=headers).json()
    assert me["email"] == "mom2@example.com"
    assert me["role"] == "member"
