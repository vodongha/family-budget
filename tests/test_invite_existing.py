"""Inviting an account that already exists → in-app invite + one-tap accept."""

from fastapi.testclient import TestClient


def _register(client: TestClient, email: str, family: str, **extra: object) -> dict[str, str]:
    payload = {
        "email": email,
        "password": "s3cret-pass",
        "display_name": email.split("@")[0],
        "family_name": family,
    }
    payload.update(extra)
    client.post("/auth/register", json=payload)
    login = client.post(
        "/auth/login", data={"username": email, "password": "s3cret-pass"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _invite_member(client: TestClient, owner_headers: dict[str, str], email: str) -> dict[str, str]:
    token = client.post(
        "/invitations", json={"email": email}, headers=owner_headers
    ).json()["token"]
    accept = client.post(
        "/invitations/accept",
        json={"token": token, "password": "p", "display_name": email.split("@")[0]},
    )
    return {"Authorization": f"Bearer {accept.json()['access_token']}"}


def test_invite_existing_email_creates_in_app_invite(client: TestClient) -> None:
    owner_a = _register(client, "a@example.com", "Family A")
    _register(client, "b@example.com", "Family B")

    invite = client.post("/invitations", json={"email": "b@example.com"}, headers=owner_a)
    assert invite.status_code == 201
    assert invite.json()["in_app"] is True


def test_existing_user_sees_inbox_and_accepts(client: TestClient) -> None:
    owner_a = _register(client, "a@example.com", "Family A")
    client.post("/wallets", json={"name": "A-Cash"}, headers=owner_a)
    member_b = _register(client, "b@example.com", "Family B")

    rid = client.post(
        "/invitations", json={"email": "b@example.com"}, headers=owner_a
    ).json()["rid"]

    inbox = client.get("/invitations/inbox", headers=member_b).json()
    assert len(inbox) == 1
    assert inbox[0]["family_name"] == "Family A"
    assert inbox[0]["rid"] == rid

    accept = client.post(f"/invitations/{rid}/accept-existing", headers=member_b)
    assert accept.status_code == 200
    moved = {"Authorization": f"Bearer {accept.json()['access_token']}"}

    me = client.get("/auth/me", headers=moved).json()
    assert me["role"] == "member"
    # Now sees Family A's wallet.
    assert [w["name"] for w in client.get("/wallets", headers=moved).json()] == ["A-Cash"]


def test_invite_existing_by_phone(client: TestClient) -> None:
    owner_a = _register(client, "a@example.com", "Family A")
    _register(client, "b@example.com", "Family B", phone="+14155552671")

    invite = client.post(
        "/invitations", json={"phone": "+14155552671"}, headers=owner_a
    )
    assert invite.status_code == 201
    assert invite.json()["in_app"] is True

    member_b = client.post(
        "/auth/login", data={"username": "b@example.com", "password": "s3cret-pass"}
    )
    headers_b = {"Authorization": f"Bearer {member_b.json()['access_token']}"}
    assert len(client.get("/invitations/inbox", headers=headers_b).json()) == 1


def test_inviting_own_member_again_is_409(client: TestClient) -> None:
    owner_a = _register(client, "a@example.com", "Family A")
    _invite_member(client, owner_a, "mom@example.com")
    resp = client.post("/invitations", json={"email": "mom@example.com"}, headers=owner_a)
    assert resp.status_code == 409


def test_owner_with_members_must_transfer_before_joining(client: TestClient) -> None:
    owner_a = _register(client, "a@example.com", "Family A")
    # b owns Family B which also has another member, so b can't just leave.
    owner_b = _register(client, "b@example.com", "Family B")
    _invite_member(client, owner_b, "c@example.com")

    rid = client.post(
        "/invitations", json={"email": "b@example.com"}, headers=owner_a
    ).json()["rid"]
    resp = client.post(f"/invitations/{rid}/accept-existing", headers=owner_b)
    assert resp.status_code == 409


def test_decline_removes_from_inbox(client: TestClient) -> None:
    owner_a = _register(client, "a@example.com", "Family A")
    member_b = _register(client, "b@example.com", "Family B")
    rid = client.post(
        "/invitations", json={"email": "b@example.com"}, headers=owner_a
    ).json()["rid"]

    assert client.post(f"/invitations/{rid}/decline", headers=member_b).status_code == 200
    assert client.get("/invitations/inbox", headers=member_b).json() == []
