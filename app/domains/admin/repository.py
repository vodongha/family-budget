"""DB access for the admin panel — deliberately CROSS-TENANT.

Unlike every other repository (which scopes by ``family_id``), the admin panel
operates over all families. These queries intentionally bypass the tenant
boundary; they must only ever be reached behind ``require_admin``.
"""

from datetime import date, datetime

from sqlalchemy import and_, false, func, or_, select, true
from sqlalchemy.orm import Session, joinedload, selectinload

from app.domains.admin.models import AdminAuditLog
from app.domains.categories.models import Category
from app.domains.transactions.models import Transaction
from app.domains.users.models import Family, User, UserRole
from app.domains.wallets.models import Wallet, WalletScope
from app.domains.wallets.repository import visibility_clause


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

    # --- single-entity getters (cross-tenant) --------------------------------

    def get_user_by_rid(self, rid: str) -> User | None:
        return self._session.scalar(
            select(User).options(joinedload(User.family)).where(User.rid == rid)
        )

    def get_family_by_rid(self, rid: str) -> Family | None:
        return self._session.scalar(select(Family).where(Family.rid == rid))

    def get_wallet_by_rid(self, rid: str) -> Wallet | None:
        return self._session.scalar(select(Wallet).where(Wallet.rid == rid))

    def get_transaction_by_rid(self, rid: str) -> Transaction | None:
        return self._session.scalar(
            select(Transaction)
            .options(
                selectinload(Transaction.wallet),
                selectinload(Transaction.category),
                selectinload(Transaction.creator),
            )
            .where(Transaction.rid == rid)
        )

    def get_category_by_rid(self, rid: str) -> Category | None:
        return self._session.scalar(select(Category).where(Category.rid == rid))

    def wallets_visible_to(self, user: User) -> list[Wallet]:
        """Every wallet the given user can see (their family's shared wallets +
        their own personal wallets)."""
        return list(
            self._session.scalars(
                select(Wallet)
                .where(visibility_clause(user.family_id, user.id, WalletScope.ALL.value))
                .order_by(Wallet.created_at)
            ).all()
        )

    def categories_for_wallet(self, wallet: Wallet) -> list[Category]:
        """Categories selectable for a transaction in this wallet — the wallet's
        family categories plus the wallet owner's personal ones, excluding
        archived."""
        conds = []
        if wallet.family_id is not None:
            conds.append(Category.family_id == wallet.family_id)
        if wallet.owner_user_id is not None:
            conds.append(Category.owner_user_id == wallet.owner_user_id)
        where = or_(*conds) if conds else false()
        return list(
            self._session.scalars(
                select(Category)
                .where(where, Category.is_archived == false())
                .order_by(Category.name)
            ).all()
        )

    def family_wallets(self, family_id: int) -> list[Wallet]:
        return list(
            self._session.scalars(
                select(Wallet)
                .where(Wallet.family_id == family_id)
                .order_by(Wallet.created_at)
            ).all()
        )

    def family_categories(self, family_id: int) -> list[Category]:
        return list(
            self._session.scalars(
                select(Category)
                .where(Category.family_id == family_id, Category.is_archived == false())
                .order_by(Category.kind, Category.name)
            ).all()
        )

    def get_budget_by_rid(self, rid: str):  # type: ignore[no-untyped-def]
        from app.domains.budgets.models import Budget

        return self._session.scalar(select(Budget).where(Budget.rid == rid))

    def family_budgets(self, family_id: int):  # type: ignore[no-untyped-def]
        from app.domains.budgets.models import Budget

        return list(
            self._session.scalars(
                select(Budget)
                .options(selectinload(Budget.category))
                .where(Budget.family_id == family_id)
            ).all()
        )

    def family_owner_id(self, family_id: int) -> int | None:
        return self._session.scalar(
            select(User.id).where(
                User.family_id == family_id, User.role == UserRole.OWNER.value
            )
        )

    def default_actor_for_wallet(self, wallet: Wallet) -> int | None:
        """A plausible ``created_by_user_id`` for an admin-created transaction in
        this wallet: the personal owner, else the wallet's creator, else the
        family owner."""
        if wallet.owner_user_id is not None:
            return wallet.owner_user_id
        if wallet.created_by_user_id is not None:
            return wallet.created_by_user_id
        if wallet.family_id is not None:
            return self.family_owner_id(wallet.family_id)
        return None

    # --- transactions (server-side paginated, cross-tenant) ------------------

    def transactions_page(
        self,
        *,
        wallet_id: int | None = None,
        family_id: int | None = None,
        created_by_user_id: int | None = None,
        type_: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        per_page: int = 25,
    ) -> tuple[list[Transaction], int]:
        conds = []
        if wallet_id is not None:
            conds.append(Transaction.wallet_id == wallet_id)
        if family_id is not None:
            conds.append(Transaction.family_id == family_id)
        if created_by_user_id is not None:
            conds.append(Transaction.created_by_user_id == created_by_user_id)
        if type_ is not None:
            conds.append(Transaction.type == type_)
        if date_from is not None:
            conds.append(Transaction.occurred_on >= date_from)
        if date_to is not None:
            conds.append(Transaction.occurred_on <= date_to)
        where = and_(*conds) if conds else true()
        total = (
            self._session.scalar(
                select(func.count()).select_from(Transaction).where(where)
            )
            or 0
        )
        rows = list(
            self._session.scalars(
                select(Transaction)
                .where(where)
                .options(
                    selectinload(Transaction.wallet),
                    selectinload(Transaction.category),
                    selectinload(Transaction.creator),
                )
                .order_by(Transaction.occurred_on.desc(), Transaction.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            ).all()
        )
        return rows, total

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
