"""Admin panel: session auth gate, login flow, and dashboard metrics."""

import re
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.domains.users.models import Family, User, UserRole, new_rid
from app.domains.wallets.models import Wallet, WalletVisibility


def _make_family(db: Session, name: str = "Vo Family") -> Family:
    f = Family(rid=new_rid(), name=name)
    db.add(f)
    db.commit()
    return f


def _csrf_from(client: TestClient, path: str) -> str:
    html = client.get(path).text
    m = re.search(r'name="csrf" value="([^"]+)"', html)
    assert m, f"no CSRF token on {path}"
    return m.group(1)


def _make_user(db: Session, email: str = "user@example.com") -> User:
    u = User(
        rid=new_rid(),
        email=email,
        hashed_password=hash_password("user-pass-123"),
        display_name="User",
        family_id=None,
        role=UserRole.MEMBER.value,
    )
    db.add(u)
    db.commit()
    return u


def _make_wallet(db: Session, owner: User) -> Wallet:
    w = Wallet(
        rid=new_rid(),
        name="Cash",
        visibility=WalletVisibility.PERSONAL.value,
        owner_user_id=owner.id,
        currency="VND",
    )
    db.add(w)
    db.commit()
    return w


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


def _login(client: TestClient) -> None:
    csrf = _csrf(client)
    client.post(
        "/admin/login",
        data={"email": "boss@example.com", "password": "admin-pass-123", "csrf": csrf},
    )


def test_list_pages_require_login(client: TestClient) -> None:
    for path in ("/admin/users", "/admin/families", "/admin/audit"):
        res = client.get(path, follow_redirects=False)
        assert res.status_code == 303
        assert res.headers["location"] == "/admin/login"


def test_list_pages_render_for_admin(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    _login(client)
    for path, marker in (
        ("/admin/users", "Users"),
        ("/admin/families", "Families"),
        ("/admin/audit", "Audit log"),
    ):
        res = client.get(path)
        assert res.status_code == 200
        assert marker in res.text
        # The datatable enhancer hook is present on list tables.
        assert 'class="dt"' in res.text or "No " in res.text


def test_users_page_lists_the_admin(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    _login(client)
    res = client.get("/admin/users")
    assert "boss@example.com" in res.text


def test_user_detail_and_edit(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    target = _make_user(db_session)
    _login(client)
    detail = client.get(f"/admin/users/{target.rid}")
    assert detail.status_code == 200
    assert "user@example.com" in detail.text

    csrf = _csrf_from(client, f"/admin/users/{target.rid}/edit")
    res = client.post(
        f"/admin/users/{target.rid}/edit",
        data={
            "display_name": "Renamed",
            "email": "user@example.com",
            "phone": "",
            "role": "member",
            "csrf": csrf,
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    db_session.refresh(target)
    assert target.display_name == "Renamed"


def test_user_soft_delete_and_restore(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    target = _make_user(db_session)
    _login(client)
    csrf = _csrf_from(client, f"/admin/users/{target.rid}")
    client.post(
        f"/admin/users/{target.rid}/delete", data={"csrf": csrf}, follow_redirects=False
    )
    db_session.refresh(target)
    assert target.is_deleted is True
    client.post(
        f"/admin/users/{target.rid}/restore", data={"csrf": csrf}, follow_redirects=False
    )
    db_session.refresh(target)
    assert target.is_deleted is False


def test_transaction_crud(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    owner = _make_user(db_session)
    wallet = _make_wallet(db_session, owner)
    _login(client)

    # create
    csrf = _csrf_from(client, f"/admin/wallets/{wallet.rid}/transactions/new")
    client.post(
        f"/admin/wallets/{wallet.rid}/transactions/new",
        data={"type": "income", "amount": "50000", "occurred_on": "2026-06-18", "csrf": csrf},
        follow_redirects=False,
    )
    detail = client.get(f"/admin/wallets/{wallet.rid}")
    assert "50000" in detail.text
    rid = re.search(r"/admin/transactions/([0-9A-Z]+)/edit", detail.text).group(1)

    # edit
    csrf = _csrf_from(client, f"/admin/transactions/{rid}/edit")
    client.post(
        f"/admin/transactions/{rid}/edit",
        data={"type": "expense", "amount": "12000", "occurred_on": "2026-06-18", "csrf": csrf},
        follow_redirects=False,
    )
    assert "12000" in client.get(f"/admin/wallets/{wallet.rid}").text

    # delete
    csrf = _csrf_from(client, f"/admin/wallets/{wallet.rid}")
    client.post(
        f"/admin/transactions/{rid}/delete", data={"csrf": csrf}, follow_redirects=False
    )
    assert "No transactions in this wallet" in client.get(f"/admin/wallets/{wallet.rid}").text


def test_transactions_page_renders(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    _login(client)
    assert client.get("/admin/transactions").status_code == 200


def test_family_detail_and_rename(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    fam = _make_family(db_session)
    _login(client)
    assert client.get(f"/admin/families/{fam.rid}").status_code == 200
    csrf = _csrf_from(client, f"/admin/families/{fam.rid}")
    client.post(
        f"/admin/families/{fam.rid}/rename",
        data={"name": "Renamed Family", "csrf": csrf},
        follow_redirects=False,
    )
    db_session.refresh(fam)
    assert fam.name == "Renamed Family"


def test_category_add_and_delete(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    fam = _make_family(db_session)
    _login(client)
    csrf = _csrf_from(client, f"/admin/families/{fam.rid}")
    client.post(
        f"/admin/families/{fam.rid}/categories",
        data={"name": "Groceries", "kind": "expense", "csrf": csrf},
        follow_redirects=False,
    )
    page = client.get(f"/admin/families/{fam.rid}").text
    assert "Groceries" in page
    rid = re.search(r"/admin/categories/([0-9A-Z]+)/delete", page).group(1)
    client.post(
        f"/admin/categories/{rid}/delete",
        data={"family_rid": fam.rid, "csrf": csrf},
        follow_redirects=False,
    )
    assert "Groceries" not in client.get(f"/admin/families/{fam.rid}").text


def test_budget_add_and_delete(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    fam = _make_family(db_session)
    _login(client)
    csrf = _csrf_from(client, f"/admin/families/{fam.rid}")
    client.post(
        f"/admin/families/{fam.rid}/categories",
        data={"name": "Bills", "kind": "expense", "csrf": csrf},
        follow_redirects=False,
    )
    page = client.get(f"/admin/families/{fam.rid}").text
    cat_rid = re.search(r"/admin/categories/([0-9A-Z]+)/delete", page).group(1)
    client.post(
        f"/admin/families/{fam.rid}/budgets",
        data={"category_rid": cat_rid, "amount": "500000", "csrf": csrf},
        follow_redirects=False,
    )
    page = client.get(f"/admin/families/{fam.rid}").text
    assert "500000" in page
    bud_rid = re.search(r"/admin/budgets/([0-9A-Z]+)/delete", page).group(1)
    client.post(
        f"/admin/budgets/{bud_rid}/delete",
        data={"family_rid": fam.rid, "csrf": csrf},
        follow_redirects=False,
    )


def test_category_and_budget_edit_forms(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    fam = _make_family(db_session)
    _login(client)
    csrf = _csrf_from(client, f"/admin/families/{fam.rid}")
    client.post(
        f"/admin/families/{fam.rid}/categories",
        data={"name": "Food", "kind": "expense", "csrf": csrf},
        follow_redirects=False,
    )
    page = client.get(f"/admin/families/{fam.rid}").text
    cat_rid = re.search(r"/admin/categories/([0-9A-Z]+)/edit", page).group(1)
    assert client.get(f"/admin/categories/{cat_rid}/edit").status_code == 200
    client.post(
        f"/admin/families/{fam.rid}/budgets",
        data={"category_rid": cat_rid, "amount": "100000", "csrf": csrf},
        follow_redirects=False,
    )
    page = client.get(f"/admin/families/{fam.rid}").text
    bud_rid = re.search(r"/admin/budgets/([0-9A-Z]+)/edit", page).group(1)
    assert client.get(f"/admin/budgets/{bud_rid}/edit").status_code == 200


def test_create_user(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    _login(client)
    assert client.get("/admin/users/new").status_code == 200
    csrf = _csrf_from(client, "/admin/users/new")
    res = client.post(
        "/admin/users",
        data={
            "email": "fresh@example.com",
            "password": "new-pass-123",
            "display_name": "Fresh",
            "csrf": csrf,
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert "fresh@example.com" in client.get("/admin/users").text


def test_hard_delete_user_cascades(client: TestClient, db_session: Session) -> None:
    from app.domains.transactions.models import Transaction, TransactionType

    _make_admin(db_session)
    owner = _make_user(db_session)
    wallet = _make_wallet(db_session, owner)
    db_session.add(
        Transaction(
            rid=new_rid(),
            wallet_id=wallet.id,
            created_by_user_id=owner.id,
            type=TransactionType.INCOME.value,
            amount=50000,
            note=None,
            occurred_on=date(2026, 6, 18),
        )
    )
    db_session.commit()
    _login(client)
    csrf = _csrf_from(client, f"/admin/users/{owner.rid}")
    res = client.post(
        f"/admin/users/{owner.rid}/purge", data={"csrf": csrf}, follow_redirects=False
    )
    assert res.status_code == 303
    assert db_session.scalar(select(User).where(User.id == owner.id)) is None
    assert (
        db_session.scalar(select(Wallet).where(Wallet.id == wallet.id)) is None
    )
    assert (
        db_session.scalar(
            select(func.count()).select_from(Transaction).where(
                Transaction.created_by_user_id == owner.id
            )
        )
        == 0
    )


def test_family_purge_detaches_members(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    fam = _make_family(db_session)
    member = _make_user(db_session, email="member@example.com")
    member.family_id = fam.id
    db_session.commit()
    _login(client)
    csrf = _csrf_from(client, f"/admin/families/{fam.rid}")
    res = client.post(
        f"/admin/families/{fam.rid}/purge", data={"csrf": csrf}, follow_redirects=False
    )
    assert res.status_code == 303
    assert db_session.scalar(select(Family).where(Family.id == fam.id)) is None
    # Member account survives, detached from the family.
    db_session.refresh(member)
    assert member.family_id is None


def test_wallet_rename_and_delete(client: TestClient, db_session: Session) -> None:
    _make_admin(db_session)
    owner = _make_user(db_session)
    wallet = _make_wallet(db_session, owner)
    _login(client)
    csrf = _csrf_from(client, f"/admin/wallets/{wallet.rid}")
    client.post(
        f"/admin/wallets/{wallet.rid}/rename",
        data={"name": "Renamed Wallet", "csrf": csrf},
        follow_redirects=False,
    )
    db_session.refresh(wallet)
    assert wallet.name == "Renamed Wallet"
    client.post(
        f"/admin/wallets/{wallet.rid}/delete",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert client.get(f"/admin/wallets/{wallet.rid}", follow_redirects=False).status_code == 303


def test_dependencies_requires_login(client: TestClient) -> None:
    res = client.get("/admin/dependencies", follow_redirects=False)
    assert res.status_code == 303


def test_dependencies_not_configured(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "github_token", "")
    _make_admin(db_session)
    _login(client)
    res = client.get("/admin/dependencies")
    assert res.status_code == 200
    assert "Not configured" in res.text  # no network call on this path


def test_dependency_alert_parser() -> None:
    from app.domains.admin.deps_panel import _parse_alert

    alert = {
        "state": "open",
        "html_url": "https://github.com/x/y/security/dependabot/1",
        "created_at": "2026-06-18T10:00:00Z",
        "security_advisory": {"severity": "HIGH", "summary": "Bad bug"},
        "security_vulnerability": {
            "package": {"name": "requests", "ecosystem": "pip"},
            "vulnerable_version_range": "< 2.32.0",
            "first_patched_version": {"identifier": "2.32.0"},
        },
    }
    parsed = _parse_alert(alert)
    assert parsed["package"] == "requests"
    assert parsed["ecosystem"] == "pip"
    assert parsed["severity"] == "high"
    assert parsed["patched"] == "2.32.0"
    assert parsed["created_at"] == "2026-06-18"


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
