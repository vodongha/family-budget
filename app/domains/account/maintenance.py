"""Scheduled purge of soft-deleted accounts (Google Play data-deletion policy).

Self-deletion only soft-deletes (sets ``is_deleted`` + ``deleted_at``). This job
makes the deletion permanent once the retention window has passed:

- **Fully-deleted families** (a sole owner deleted their account) are hard-purged
  together with all of their data — transactions, wallets, invitations, members.
- **Members** who deleted their account inside a still-active family are
  **anonymised** instead of removed: their rows are referenced by shared family
  transactions (``created_by_user_id`` is NOT NULL), so the row is kept but all
  personal data (email, name, password) is scrubbed.

The pure function ``purge_expired_accounts`` is engine-agnostic and unit-tested on
SQLite; ``purge_expired_accounts_task`` is the Celery Beat entry point.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, true
from sqlalchemy.orm import Session

from app.domains.categories.models import Category
from app.domains.invitations.models import Invitation
from app.domains.transactions.models import Transaction
from app.domains.users.models import Family, User
from app.domains.wallets.models import Wallet

RETENTION_DAYS = 30


def purge_expired_accounts(
    session: Session,
    *,
    now: datetime | None = None,
    retention_days: int = RETENTION_DAYS,
) -> dict[str, int]:
    """Purge/anonymise accounts whose soft-deletion is older than the window.

    Returns a small summary for logging. Commits once at the end.
    """
    if now is None:
        now = datetime.now(UTC).replace(tzinfo=None)
    cutoff = now - timedelta(days=retention_days)
    summary = {"families_purged": 0, "members_anonymised": 0}

    # 1) Fully-deleted families → hard purge, children first to satisfy FKs.
    family_ids = list(
        session.scalars(
            select(Family.id).where(
                Family.is_deleted == true(), Family.deleted_at < cutoff
            )
        )
    )
    for family_id in family_ids:
        session.execute(delete(Transaction).where(Transaction.family_id == family_id))
        session.execute(delete(Category).where(Category.family_id == family_id))
        session.execute(delete(Wallet).where(Wallet.family_id == family_id))
        session.execute(delete(Invitation).where(Invitation.family_id == family_id))
        session.execute(delete(User).where(User.family_id == family_id))
        session.execute(delete(Family).where(Family.id == family_id))
        summary["families_purged"] += 1

    # 2) Members deleted inside a still-active family → scrub PII, keep the row
    #    (members of purged families were already removed in step 1).
    members = list(
        session.scalars(
            select(User).where(
                User.is_deleted == true(), User.deleted_at < cutoff
            )
        )
    )
    for user in members:
        # Their personal wallets are private data no one else can see — purge
        # them (and their transactions) rather than leave them orphaned. Shared
        # family wallets/transactions stay; the member row is only anonymised.
        personal_wallet_ids = list(
            session.scalars(
                select(Wallet.id).where(Wallet.owner_user_id == user.id)
            )
        )
        if personal_wallet_ids:
            session.execute(
                delete(Transaction).where(
                    Transaction.wallet_id.in_(personal_wallet_ids)
                )
            )
            session.execute(
                delete(Wallet).where(Wallet.id.in_(personal_wallet_ids))
            )
        user.email = f"deleted+{user.rid}@deleted.invalid"
        user.display_name = "Deleted user"
        user.hashed_password = ""
        summary["members_anonymised"] += 1

    session.commit()
    return summary
