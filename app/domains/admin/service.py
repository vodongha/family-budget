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
from app.domains.users.models import User
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

    @staticmethod
    def now() -> datetime:
        from datetime import UTC

        return datetime.now(UTC).replace(tzinfo=None)
