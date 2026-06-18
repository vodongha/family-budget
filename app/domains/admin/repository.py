"""DB access for the admin panel — deliberately CROSS-TENANT.

Unlike every other repository (which scopes by ``family_id``), the admin panel
operates over all families. These queries intentionally bypass the tenant
boundary; they must only ever be reached behind ``require_admin``.
"""

from datetime import datetime

from sqlalchemy import false, func, select, true
from sqlalchemy.orm import Session, joinedload

from app.domains.admin.models import AdminAuditLog
from app.domains.transactions.models import Transaction
from app.domains.users.models import Family, User
from app.domains.wallets.models import Wallet


class AdminRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # --- metrics (dashboard) -------------------------------------------------

    def _count(self, stmt) -> int:  # type: ignore[no-untyped-def]
        return self._session.scalar(stmt) or 0

    def metrics(self) -> dict[str, int]:
        """Cheap platform-wide counts for the dashboard. Oracle has no native
        boolean, so flags are filtered with ``== true()/false()`` (never
        ``.is_()``)."""
        return {
            "users_total": self._count(select(func.count()).select_from(User)),
            "users_active": self._count(
                select(func.count())
                .select_from(User)
                .where(User.is_deleted == false())
            ),
            "users_deleted": self._count(
                select(func.count())
                .select_from(User)
                .where(User.is_deleted == true())
            ),
            "admins": self._count(
                select(func.count())
                .select_from(User)
                .where(User.is_superadmin == true())
            ),
            "families_total": self._count(
                select(func.count()).select_from(Family)
            ),
            "families_active": self._count(
                select(func.count())
                .select_from(Family)
                .where(Family.is_deleted == false())
            ),
            "families_deleted": self._count(
                select(func.count())
                .select_from(Family)
                .where(Family.is_deleted == true())
            ),
            "wallets_total": self._count(
                select(func.count()).select_from(Wallet)
            ),
            "transactions_total": self._count(
                select(func.count()).select_from(Transaction)
            ),
        }

    # --- listings (read-only; client-side datatable handles sort/search/page) -

    def list_users(self, limit: int = 1000) -> list[User]:
        return list(
            self._session.scalars(
                select(User)
                .options(joinedload(User.family))
                .order_by(User.created_at.desc())
                .limit(limit)
            ).all()
        )

    def list_families(self, limit: int = 1000) -> list[Family]:
        return list(
            self._session.scalars(
                select(Family).order_by(Family.created_at.desc()).limit(limit)
            ).all()
        )

    def _counts_by_family(self, column) -> dict[int, int]:  # type: ignore[no-untyped-def]
        rows = self._session.execute(
            select(column, func.count())
            .where(column.is_not(None))
            .group_by(column)
        ).all()
        return {fid: count for fid, count in rows}

    def family_member_counts(self) -> dict[int, int]:
        return self._counts_by_family(User.family_id)

    def family_wallet_counts(self) -> dict[int, int]:
        return self._counts_by_family(Wallet.family_id)

    # --- audit log -----------------------------------------------------------

    def add_audit(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        target_type: str | None = None,
        target_rid: str | None = None,
        detail: str | None = None,
    ) -> AdminAuditLog:
        entry = AdminAuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_rid=target_rid,
            detail=detail,
        )
        self._session.add(entry)
        return entry

    def recent_audit(self, limit: int = 20) -> list[AdminAuditLog]:
        return list(
            self._session.scalars(
                select(AdminAuditLog)
                .order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
                .limit(limit)
            ).all()
        )

    def latest_rate_updated_at(self) -> datetime | None:
        """Most recent exchange-rate refresh time (for the Ops panel)."""
        from app.domains.rates.models import ExchangeRate

        return self._session.scalar(select(func.max(ExchangeRate.updated_at)))
