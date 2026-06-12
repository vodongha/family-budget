"""Sign in with Google — the ID token verifier is mocked (no network)."""

import pytest
from fastapi.testclient import TestClient

import app.domains.auth.service as auth_service


def _mock_verifier(monkeypatch: pytest.MonkeyPatch, claims: dict[str, str]) -> None:
    monkeypatch.setattr(
        auth_service, "verify_google_id_token", lambda token, client_ids: claims
    )


def test_google_login_new_user_creates_family_owner(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    assert me["role"] == "owner"


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
