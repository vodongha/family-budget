"""Profile update + account deletion (Google Play policy) + scheduled purge."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.account.maintenance import purge_expired_accounts
from app.domains.transactions.models import Transaction
from app.domains.users.models import Family, User
from app.domains.wallets.models import Wallet


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


def _invite_member(client: TestClient, owner_headers: dict[str, str], email: str) -> dict[str, str]:
    invite = client.post(
        "/invitations", json={"email": email}, headers=owner_headers
    ).json()
    accept = client.post(
        "/invitations/accept",
        json={"token": invite["token"], "password": "her-pass", "display_name": "Mom"},
    )
    return {"Authorization": f"Bearer {accept.json()['access_token']}"}


def _age_deletion(session: Session, email: str, days: int) -> None:
    """Backdate a soft-deleted user's (and its deleted family's) deleted_at."""
    old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    user = session.scalar(select(User).where(User.email == email))
    assert user is not None
    user.deleted_at = old
    fam = session.get(Family, user.family_id)
    if fam is not None and fam.is_deleted:
        fam.deleted_at = old
    session.commit()


# --- profile update -------------------------------------------------------

def test_update_display_name(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.patch(
        "/auth/me", json={"display_name": "New Name"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "New Name"
    assert client.get("/auth/me", headers=auth_headers).json()["display_name"] == "New Name"


def test_update_display_name_rejects_empty(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.patch("/auth/me", json={"display_name": ""}, headers=auth_headers)
    assert resp.status_code == 422


# --- deletion -------------------------------------------------------------

def test_member_can_delete_then_cannot_use_account(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    member = _invite_member(client, auth_headers, "mom@example.com")

    resp = client.delete("/auth/me", headers=member)
    assert resp.status_code == 204

    # Token is rejected immediately even though it's otherwise valid.
    assert client.get("/auth/me", headers=member).status_code == 401
    # And login no longer works.
    relogin = client.post(
        "/auth/login", data={"username": "mom@example.com", "password": "her-pass"}
    )
    assert relogin.status_code == 401


def test_owner_with_members_cannot_delete(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    _invite_member(client, auth_headers, "mom@example.com")
    resp = client.delete("/auth/me", headers=auth_headers)
    assert resp.status_code == 409
    # Still usable.
    assert client.get("/auth/me", headers=auth_headers).status_code == 200


def test_sole_owner_delete_marks_family_deleted(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    me = client.get("/auth/me", headers=auth_headers).json()
    resp = client.delete("/auth/me", headers=auth_headers)
    assert resp.status_code == 204

    user = db_session.scalar(select(User).where(User.rid == me["rid"]))
    assert user is not None and user.is_deleted
    family = db_session.get(Family, user.family_id)
    assert family is not None and family.is_deleted


# --- scheduled purge ------------------------------------------------------

def test_purge_within_window_keeps_data(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    client.delete("/auth/me", headers=auth_headers)  # soft-deleted just now
    summary = purge_expired_accounts(db_session)
    assert summary == {"families_purged": 0, "members_anonymised": 0}
    assert db_session.scalar(select(func.count()).select_from(User)) == 1


def test_purge_removes_expired_family_and_all_data(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    client.post("/wallets", json={"name": "Cash"}, headers=auth_headers)
    wallet = client.get("/wallets", headers=auth_headers).json()[0]
    client.post(
        "/transactions",
        json={"wallet_rid": wallet["rid"], "type": "income", "amount": 1000},
        headers=auth_headers,
    )
    client.delete("/auth/me", headers=auth_headers)  # sole owner → family deleted
    _age_deletion(db_session, "dad@example.com", days=31)

    summary = purge_expired_accounts(db_session)
    assert summary["families_purged"] == 1

    assert db_session.scalar(select(func.count()).select_from(User)) == 0
    assert db_session.scalar(select(func.count()).select_from(Family)) == 0
    assert db_session.scalar(select(func.count()).select_from(Wallet)) == 0
    assert db_session.scalar(select(func.count()).select_from(Transaction)) == 0


def test_purge_anonymises_expired_member_but_keeps_row(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    member = _invite_member(client, auth_headers, "mom@example.com")
    # Member records a transaction, so their row is referenced by family data.
    client.post("/wallets", json={"name": "Cash"}, headers=auth_headers)
    wallet = client.get("/wallets", headers=auth_headers).json()[0]
    client.post(
        "/transactions",
        json={"wallet_rid": wallet["rid"], "type": "expense", "amount": 500},
        headers=member,
    )
    client.delete("/auth/me", headers=member)
    _age_deletion(db_session, "mom@example.com", days=31)

    summary = purge_expired_accounts(db_session)
    assert summary["families_purged"] == 0
    assert summary["members_anonymised"] == 1

    # Row kept (FK from the transaction), but PII scrubbed.
    user = db_session.scalar(
        select(User).where(User.display_name == "Deleted user")
    )
    assert user is not None
    assert user.email.startswith("deleted+")
    assert user.email.endswith("@deleted.invalid")
    assert user.hashed_password == ""
    # Family + owner + the transaction remain intact.
    assert db_session.scalar(select(func.count()).select_from(Transaction)) == 1
