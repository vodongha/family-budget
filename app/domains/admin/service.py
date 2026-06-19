"""Admin panel business logic — stateless; the session is passed in per call.

Reachable only behind ``require_admin``; these methods assume the caller is an
authenticated super-admin.
"""

from datetime import date, datetime
from math import ceil

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.domains.admin.models import AdminAuditLog
from app.domains.admin.repository import AdminRepository
from app.domains.transactions.models import Transaction, TransactionType
from app.domains.transactions.repository import TransactionRepository
from app.domains.users.models import Family, User
from app.domains.wallets.models import Wallet
from app.domains.wallets.repository import WalletRepository


class AdminService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = AdminRepository(session)
        self._wallets = WalletRepository(session)
        self._txns = TransactionRepository(session)

    def authenticate(self, email: str, password: str) -> User | None:
        """Verify admin credentials. Returns the user only if they are an active
        super-admin with a matching password; otherwise ``None`` (the caller
        shows one generic error, never leaking which check failed)."""
        email = email.strip().lower()
        user = self._session.scalar(
            select(User).where(func.lower(User.email) == email)
        )
        if (
            user is None
            or user.is_deleted
            or not user.is_superadmin
            or not user.hashed_password
            or not verify_password(password, user.hashed_password)
        ):
            return None
        return user

    def get_active_admin(self, rid: str) -> User | None:
        """Load a super-admin by rid, or ``None`` if missing / deleted / no longer
        an admin (so a revoked admin's live session stops working)."""
        user = self._session.scalar(select(User).where(User.rid == rid))
        if user is None or user.is_deleted or not user.is_superadmin:
            return None
        return user

    def dashboard(self) -> dict[str, object]:
        return {
            "metrics": self._repo.metrics(),
            "rates_updated_at": self._repo.latest_rate_updated_at(),
            "recent_audit": self._repo.recent_audit(limit=10),
        }

    def recent_audit(self, limit: int = 50) -> list[AdminAuditLog]:
        return self._repo.recent_audit(limit=limit)

    def list_users(self) -> list[User]:
        return self._repo.list_users()

    def list_families(self) -> list[dict[str, object]]:
        """Families with their derived member + wallet counts, for the list page."""
        members = self._repo.family_member_counts()
        wallets = self._repo.family_wallet_counts()
        return [
            {
                "family": f,
                "members": members.get(f.id, 0),
                "wallets": wallets.get(f.id, 0),
            }
            for f in self._repo.list_families()
        ]

    def log(
        self,
        actor: User,
        action: str,
        *,
        target_type: str | None = None,
        target_rid: str | None = None,
        detail: str | None = None,
    ) -> None:
        """Record an admin action and commit. Call after the mutation succeeds."""
        self._repo.add_audit(
            actor_user_id=actor.id,
            action=action,
            target_type=target_type,
            target_rid=target_rid,
            detail=detail,
        )
        self._session.commit()

    # --- users ---------------------------------------------------------------

    def get_user(self, rid: str) -> User | None:
        return self._repo.get_user_by_rid(rid)

    def user_wallets(self, user: User) -> list[dict[str, object]]:
        wallets = self._repo.wallets_visible_to(user)
        balances = self._wallets.balances_by_wallet([w.id for w in wallets])
        return [{"wallet": w, "balance": balances.get(w.id, 0)} for w in wallets]

    def create_user(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        phone: str | None,
        role: str,
        is_superadmin: bool,
        family_id: int | None,
    ) -> User:
        from app.domains.categories.repository import CategoryRepository
        from app.domains.users.models import new_rid

        user = User(
            rid=new_rid(),
            email=email.strip().lower(),
            hashed_password=hash_password(password),
            display_name=display_name.strip(),
            phone=(phone or "").strip() or None,
            family_id=family_id,
            role=role,
            is_superadmin=is_superadmin,
        )
        self._session.add(user)
        self._session.flush()
        # Seed a personal category set so a family-less account is usable at once
        # (mirrors registration); family accounts already have their own set.
        if family_id is None:
            CategoryRepository(self._session).seed_defaults(owner_user_id=user.id)
        self._session.commit()
        return user

    def hard_delete_user(self, user: User) -> dict[str, int]:
        """Permanently delete a user **and all their related data** — every
        transaction they created (family or personal, both transfer legs), their
        personal wallets, their budgets and personal categories, and their
        invitations. Shared wallets they created keep their rows (the creator
        link is just cleared); shared categories stay. Returns a small summary.
        """
        from sqlalchemy import delete, or_, update

        from app.domains.budgets.models import Budget
        from app.domains.categories.models import Category
        from app.domains.invitations.models import Invitation
        from app.domains.transactions.models import Transaction
        from app.domains.wallets.models import Wallet

        uid = user.id
        s = self._session
        summary = {"transactions": 0, "wallets": 0, "budgets": 0, "categories": 0}

        # 1) Every transaction this user created (covers family + personal wallets
        #    and both legs of any transfer). Done first so nothing references the
        #    wallets/categories removed below.
        summary["transactions"] = int(
            s.execute(
                delete(Transaction).where(Transaction.created_by_user_id == uid)
            ).rowcount
            or 0
        )

        # 2) Personal wallets (owned by this user): drop any residual transactions
        #    then the wallets.
        pw_ids = list(s.scalars(select(Wallet.id).where(Wallet.owner_user_id == uid)))
        if pw_ids:
            s.execute(delete(Transaction).where(Transaction.wallet_id.in_(pw_ids)))
            summary["wallets"] = int(
                s.execute(delete(Wallet).where(Wallet.id.in_(pw_ids))).rowcount or 0
            )
        # Shared wallets they created stay — just clear the creator link.
        s.execute(
            update(Wallet)
            .where(Wallet.created_by_user_id == uid)
            .values(created_by_user_id=None)
        )

        # 3) Budgets owned/created by the user.
        summary["budgets"] = int(
            s.execute(
                delete(Budget).where(
                    or_(Budget.owner_user_id == uid, Budget.created_by_user_id == uid)
                )
            ).rowcount
            or 0
        )

        # 4) Their personal categories — detach from any other transactions first.
        cat_ids = list(
            s.scalars(select(Category.id).where(Category.owner_user_id == uid))
        )
        if cat_ids:
            s.execute(
                update(Transaction)
                .where(Transaction.category_id.in_(cat_ids))
                .values(category_id=None)
            )
            summary["categories"] = int(
                s.execute(delete(Category).where(Category.id.in_(cat_ids))).rowcount
                or 0
            )

        # 5) Invitations they sent; null them out where they were the target.
        s.execute(delete(Invitation).where(Invitation.invited_by_user_id == uid))
        s.execute(
            update(Invitation)
            .where(Invitation.target_user_id == uid)
            .values(target_user_id=None)
        )

        # 6) Finally the user (admin_audit_log.actor_user_id is ON DELETE SET NULL).
        s.execute(delete(User).where(User.id == uid))
        s.commit()
        return summary

    def active_families(self) -> list[Family]:  # type: ignore[no-untyped-def]
        return self._repo.list_families()

    def update_user(
        self,
        user: User,
        *,
        display_name: str,
        email: str,
        phone: str | None,
        role: str,
        is_superadmin: bool,
    ) -> None:
        user.display_name = display_name.strip()
        user.email = email.strip().lower()
        user.phone = (phone or "").strip() or None
        user.role = role
        user.is_superadmin = is_superadmin
        self._session.commit()

    def set_user_deleted(self, user: User, deleted: bool) -> None:
        user.is_deleted = deleted
        user.deleted_at = self.now() if deleted else None
        if deleted:
            user.google_sub = None  # unlink, mirroring self-service deletion
        self._session.commit()

    def reset_password(self, user: User, new_password: str) -> None:
        user.hashed_password = hash_password(new_password)
        self._session.commit()

    def unlink_google(self, user: User) -> None:
        user.google_sub = None
        self._session.commit()

    # --- wallets / transactions ---------------------------------------------

    def get_wallet(self, rid: str) -> Wallet | None:
        return self._repo.get_wallet_by_rid(rid)

    def wallet_balance(self, wallet: Wallet) -> int:
        return self._wallets.balance(wallet.id)

    def categories_for_wallet(self, wallet: Wallet):  # type: ignore[no-untyped-def]
        return self._repo.categories_for_wallet(wallet)

    def get_transaction(self, rid: str) -> Transaction | None:
        return self._repo.get_transaction_by_rid(rid)

    def get_category(self, rid: str):  # type: ignore[no-untyped-def]
        return self._repo.get_category_by_rid(rid)

    def transactions(
        self, *, page: int = 1, per_page: int = 25, **filters: object
    ) -> dict[str, object]:
        rows, total = self._repo.transactions_page(
            page=page, per_page=per_page, **filters  # type: ignore[arg-type]
        )
        return {
            "rows": rows,
            "total": total,
            "page": page,
            "pages": max(1, ceil(total / per_page)),
            "per_page": per_page,
        }

    def transactions_all(self, *, cap: int = 2000, **filters: object):  # type: ignore[no-untyped-def]
        """All matching transactions (newest first), capped — the client-side
        datatable handles sort/search/pagination, so every admin table looks the
        same. ``cap`` guards against an unbounded load."""
        rows, _ = self._repo.transactions_page(
            page=1, per_page=cap, **filters  # type: ignore[arg-type]
        )
        return rows

    def create_transaction(
        self,
        actor: User,
        wallet: Wallet,
        *,
        type_: TransactionType,
        amount_minor: int,
        note: str | None,
        occurred_on: date,
        category_id: int | None,
    ) -> Transaction:
        creator = self._repo.default_actor_for_wallet(wallet) or actor.id
        txn = self._txns.add(
            family_id=wallet.family_id,
            wallet_id=wallet.id,
            created_by_user_id=creator,
            type_=type_,
            amount=amount_minor,
            note=note,
            occurred_on=occurred_on,
            category_id=category_id,
        )
        self._session.commit()
        return txn

    def update_transaction(
        self,
        txn: Transaction,
        wallet: Wallet,
        *,
        type_: TransactionType,
        amount_minor: int,
        note: str | None,
        occurred_on: date,
        category_id: int | None,
    ) -> None:
        txn.wallet_id = wallet.id
        txn.family_id = wallet.family_id
        txn.type = type_.value
        txn.amount = amount_minor
        txn.note = note
        txn.occurred_on = occurred_on
        txn.category_id = category_id
        self._session.commit()

    def delete_transaction(self, txn: Transaction) -> int:
        """Delete a transaction; a transfer leg takes its paired leg with it.
        Returns the number of rows removed."""
        if txn.transfer_group_rid:
            legs = self._txns.list_by_transfer_group(txn.transfer_group_rid)
        else:
            legs = [txn]
        for leg in legs:
            self._txns.delete(leg)
        self._session.commit()
        return len(legs)

    # --- families ------------------------------------------------------------

    def get_family(self, rid: str):  # type: ignore[no-untyped-def]
        return self._repo.get_family_by_rid(rid)

    def get_family_by_id(self, family_id: int):  # type: ignore[no-untyped-def]
        return self._repo.get_family_by_id(family_id)

    def family_overview(self, family) -> dict[str, object]:  # type: ignore[no-untyped-def]
        from app.domains.families.repository import FamilyRepository

        wallets = self._repo.family_wallets(family.id)
        balances = self._wallets.balances_by_wallet([w.id for w in wallets])
        return {
            "members": FamilyRepository(self._session).list_active_members(family.id),
            "wallets": [{"wallet": w, "balance": balances.get(w.id, 0)} for w in wallets],
            "categories": self._repo.family_categories(family.id),
            "budgets": self._repo.family_budgets(family.id),
        }

    def rename_family(self, family, name: str) -> None:  # type: ignore[no-untyped-def]
        family.name = name.strip()
        self._session.commit()

    def set_family_deleted(self, family, deleted: bool) -> None:  # type: ignore[no-untyped-def]
        family.is_deleted = deleted
        family.deleted_at = self.now() if deleted else None
        self._session.commit()

    def purge_family(self, family) -> None:  # type: ignore[no-untyped-def]
        """Permanently delete the family + shared data; members are detached."""
        self._repo.purge_family(family)
        self._session.commit()

    # --- wallets (edit / delete) --------------------------------------------

    def rename_wallet(self, wallet: Wallet, name: str) -> None:
        wallet.name = name.strip()
        self._session.commit()

    def delete_wallet(self, wallet: Wallet) -> int:
        removed = self._wallets.delete_with_transactions(wallet.id)
        self._session.commit()
        return removed

    # --- categories ----------------------------------------------------------

    def add_category(self, family, *, name, icon, color, kind):  # type: ignore[no-untyped-def]
        from app.domains.categories.models import CategoryKind
        from app.domains.categories.repository import CategoryRepository

        cat = CategoryRepository(self._session).add(
            family_id=family.id,
            owner_user_id=None,
            name=name.strip(),
            icon=(icon or "").strip() or None,
            color=(color or "").strip() or None,
            kind=CategoryKind(kind),
        )
        self._session.commit()
        return cat

    def update_category(self, category, *, name, icon, color):  # type: ignore[no-untyped-def]
        category.name = name.strip()
        category.icon = (icon or "").strip() or None
        category.color = (color or "").strip() or None
        self._session.commit()

    def delete_category(self, category) -> None:  # type: ignore[no-untyped-def]
        from app.domains.categories.repository import CategoryRepository

        repo = CategoryRepository(self._session)
        repo.clear_from_transactions(category.id)
        repo.delete(category)
        self._session.commit()

    # --- budgets -------------------------------------------------------------

    def get_budget(self, rid: str):  # type: ignore[no-untyped-def]
        return self._repo.get_budget_by_rid(rid)

    def add_budget(self, family, *, category, amount_base: int, actor):  # type: ignore[no-untyped-def]
        from app.domains.budgets.repository import BudgetRepository

        budget = BudgetRepository(self._session).add(
            family_id=family.id,
            owner_user_id=None,
            category_id=category.id,
            amount=amount_base,
            created_by_user_id=actor.id,
        )
        self._session.commit()
        return budget

    def update_budget(self, budget, amount_base: int) -> None:  # type: ignore[no-untyped-def]
        budget.amount = amount_base
        self._session.commit()

    def delete_budget(self, budget) -> None:  # type: ignore[no-untyped-def]
        from app.domains.budgets.repository import BudgetRepository

        BudgetRepository(self._session).delete(budget)
        self._session.commit()

    @staticmethod
    def now() -> datetime:
        from datetime import UTC

        return datetime.now(UTC).replace(tzinfo=None)
