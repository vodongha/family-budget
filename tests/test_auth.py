"""Auth flow: register → login → /me, scoped to a family."""

from fastapi.testclient import TestClient


def _register(client: TestClient) -> dict:
    resp = client.post(
        "/auth/register",
        json={
            "email": "dad@example.com",
            "password": "s3cret-pass",
            "display_name": "Dad",
            "family_name": "Vo Family",
        },
    )
    return resp


def test_register_creates_user_in_a_family(client: TestClient) -> None:
    resp = _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "dad@example.com"
    assert body["family_id"] is not None
    assert len(body["rid"]) == 26  # ULID


def test_register_duplicate_email_is_rejected(client: TestClient) -> None:
    _register(client)
    resp = _register(client)
    assert resp.status_code == 409


def test_login_then_me_returns_current_user(client: TestClient) -> None:
    _register(client)
    login = client.post(
        "/auth/login",
        data={"username": "dad@example.com", "password": "s3cret-pass"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "dad@example.com"


def test_login_wrong_password_is_unauthorized(client: TestClient) -> None:
    _register(client)
    login = client.post(
        "/auth/login",
        data={"username": "dad@example.com", "password": "wrong"},
    )
    assert login.status_code == 401


def test_me_without_token_is_unauthorized(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401


def test_change_password_updates_login(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # auth_headers = dad@example.com / s3cret-pass, has_password True.
    assert client.get("/auth/me", headers=auth_headers).json()["has_password"] is True
    resp = client.post(
        "/auth/change-password",
        json={"current_password": "s3cret-pass", "new_password": "new-s3cret-1"},
        headers=auth_headers,
    )
    assert resp.status_code == 204
    # Old password no longer works; new one does.
    assert (
        client.post(
            "/auth/login",
            data={"username": "dad@example.com", "password": "s3cret-pass"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login",
            data={"username": "dad@example.com", "password": "new-s3cret-1"},
        ).status_code
        == 200
    )


def test_change_password_wrong_current_is_400(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/auth/change-password",
        json={"current_password": "wrong", "new_password": "new-s3cret-1"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
