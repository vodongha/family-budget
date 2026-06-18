"""Admin panel: session auth gate, login flow, and dashboard metrics."""

import re

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.domains.users.models import User, UserRole, new_rid


def _make_admin(
    db: Session,
    email: str = "boss@example.com",
    password: str = "admin-pass-123",
    *,
    is_superadmin: bool = True,
) -> User:
    user = User(
        rid=new_rid(),
        email=email,
        hashed_password=hash_password(password),
        display_name="Boss",
        family_id=None,
        role=UserRole.MEMBER.value,
        is_superadmin=is_superadmin,
    )
    db.add(user)
    db.commit()
    return user


def _csrf(client: TestClient) -> str:
    html = client.get("/admin/login").text
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match, "login page should expose a CSRF token"
    return match.group(1)


def test_dashboard_requires_login(client: TestClient) -> None:
    res = client.get("/admin", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/admin/login"


def test_login_success_then_dashboard(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    csrf = _csrf(client)
    res = client.post(
        "/admin/login",
        data={"email": "boss@example.com", "password": "admin-pass-123", "csrf": csrf},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"] == "/admin"

    dash = client.get("/admin")
    assert dash.status_code == 200
    assert "Dashboard" in dash.text


def test_login_rejects_non_admin(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session, email="user@example.com", is_superadmin=False)
    csrf = _csrf(client)
    res = client.post(
        "/admin/login",
        data={"email": "user@example.com", "password": "admin-pass-123", "csrf": csrf},
        follow_redirects=False,
    )
    assert res.status_code == 401
    assert "Invalid credentials" in res.text


def test_login_rejects_bad_password(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    csrf = _csrf(client)
    res = client.post(
        "/admin/login",
        data={"email": "boss@example.com", "password": "wrong", "csrf": csrf},
        follow_redirects=False,
    )
    assert res.status_code == 401


def test_login_rejects_bad_csrf(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    _csrf(client)  # establish a session token
    res = client.post(
        "/admin/login",
        data={"email": "boss@example.com", "password": "admin-pass-123", "csrf": "nope"},
        follow_redirects=False,
    )
    # Bad CSRF bounces back to the login page rather than authenticating.
    assert res.status_code == 303
    assert res.headers["location"] == "/admin/login"


def test_dashboard_shows_user_count(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    csrf = _csrf(client)
    client.post(
        "/admin/login",
        data={"email": "boss@example.com", "password": "admin-pass-123", "csrf": csrf},
    )
    dash = client.get("/admin")
    # One user exists (the admin) and it is counted among admins.
    assert "Users" in dash.text
    assert "Admins" in dash.text


def test_logout_clears_session(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    csrf = _csrf(client)
    client.post(
        "/admin/login",
        data={"email": "boss@example.com", "password": "admin-pass-123", "csrf": csrf},
    )
    assert client.get("/admin", follow_redirects=False).status_code == 200
    client.post("/admin/logout", data={"csrf": csrf}, follow_redirects=False)
    assert client.get("/admin", follow_redirects=False).status_code == 303
