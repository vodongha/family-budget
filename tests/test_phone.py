"""Optional phone number: validation, normalisation, uniqueness."""

from fastapi.testclient import TestClient

VALID = "+14155552671"  # a valid US number
VALID_E164_FROM_LOCAL = "+12025550123"


def _register(client: TestClient, email: str, **extra: object) -> dict:
    payload = {
        "email": email,
        "password": "s3cret-pass",
        "display_name": email.split("@")[0],
        "family_name": "Fam",
    }
    payload.update(extra)
    return client.post("/auth/register", json=payload)


def test_register_without_phone_is_ok(client: TestClient) -> None:
    resp = _register(client, "nophone@example.com")
    assert resp.status_code == 201
    assert resp.json()["phone"] is None


def test_register_normalises_phone_to_e164(client: TestClient) -> None:
    resp = _register(client, "p@example.com", phone="+1 (415) 555-2671")
    assert resp.status_code == 201
    assert resp.json()["phone"] == VALID


def test_register_with_invalid_phone_is_422(client: TestClient) -> None:
    resp = _register(client, "bad@example.com", phone="123")
    assert resp.status_code == 422


def test_duplicate_phone_is_409(client: TestClient) -> None:
    assert _register(client, "first@example.com", phone=VALID).status_code == 201
    dup = _register(client, "second@example.com", phone=VALID)
    assert dup.status_code == 409


def test_update_profile_sets_and_clears_phone(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    set_resp = client.patch(
        "/auth/me",
        json={"display_name": "Dad", "phone": VALID_E164_FROM_LOCAL},
        headers=auth_headers,
    )
    assert set_resp.status_code == 200
    assert set_resp.json()["phone"] == VALID_E164_FROM_LOCAL

    clear_resp = client.patch(
        "/auth/me", json={"display_name": "Dad", "phone": ""}, headers=auth_headers
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json()["phone"] is None


def test_update_profile_rejects_invalid_phone(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.patch(
        "/auth/me", json={"display_name": "Dad", "phone": "abc"}, headers=auth_headers
    )
    assert resp.status_code == 422
