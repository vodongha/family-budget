"""Sign in with Google — the ID token verifier is mocked (no network)."""

import pytest
from fastapi.testclient import TestClient

import app.domains.auth.service as auth_service


def _mock_verifier(monkeypatch: pytest.MonkeyPatch, claims: dict[str, str]) -> None:
    monkeypatch.setattr(
        auth_service, "verify_google_id_token", lambda token, client_ids: claims
    )


def test_google_login_new_user_has_no_family(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A brand-new Google account starts with no family — it creates or joins one
    # after first sign-in (same as password registration).
    _mock_verifier(
        monkeypatch,
        {"sub": "g-1", "email": "new@example.com", "name": "New Person"},
    )
    resp = client.post("/auth/google", json={"id_token": "fake"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["email"] == "new@example.com"
    assert me["display_name"] == "New Person"
    assert me["family_id"] is None
    assert me["has_family"] is False


def test_google_login_links_existing_email(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # auth_headers registered dad@example.com with a password + owns "Vo Family".
    me_before = client.get("/auth/me", headers=auth_headers).json()
    _mock_verifier(
        monkeypatch,
        {"sub": "g-dad", "email": "dad@example.com", "name": "Dad"},
    )
    resp = client.post("/auth/google", json={"id_token": "fake"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    # Same account (same rid + family), now linked to Google — not a new family.
    assert me["rid"] == me_before["rid"]
    assert me["family_id"] == me_before["family_id"]


def test_google_links_existing_email_case_insensitively(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # auth_headers registered dad@example.com (lowercased on store). A Google
    # token with different casing must link to the same account, not make a new
    # one.
    me_before = client.get("/auth/me", headers=auth_headers).json()
    _mock_verifier(
        monkeypatch,
        {"sub": "g-case", "email": "DAD@Example.com", "name": "Dad"},
    )
    resp = client.post("/auth/google", json={"id_token": "fake"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["rid"] == me_before["rid"]
    assert me["family_id"] == me_before["family_id"]


def test_google_only_user_cannot_password_login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_verifier(
        monkeypatch,
        {"sub": "g-2", "email": "goo@example.com", "name": "Goo"},
    )
    client.post("/auth/google", json={"id_token": "fake"})

    # No password was ever set → password login must fail.
    resp = client.post(
        "/auth/login", data={"username": "goo@example.com", "password": "anything"}
    )
    assert resp.status_code == 401


def test_google_only_user_can_set_password(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_verifier(
        monkeypatch,
        {"sub": "g-3", "email": "goo2@example.com", "name": "Goo2"},
    )
    token = client.post("/auth/google", json={"id_token": "fake"}).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=headers).json()["has_password"] is False

    # A Google-only account sets its first password without a current one.
    resp = client.post(
        "/auth/change-password",
        json={"new_password": "brand-new-1"},
        headers=headers,
    )
    assert resp.status_code == 204
    # Now password login works.
    assert (
        client.post(
            "/auth/login",
            data={"username": "goo2@example.com", "password": "brand-new-1"},
        ).status_code
        == 200
    )
