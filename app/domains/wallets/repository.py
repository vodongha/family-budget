"""DB access for wallets. Always scoped by family_id (tenant boundary).

Wallet privacy is enforced here too: a personal wallet is only ever returned to
its ``owner_user_id``. Every read goes through :func:`visibility_clause`, so the
filter can't be forgotten at a call site.
"""

# A method named ``list`` shadows the builtin in the class body, so ``list[int]``
# annotations on later methods must stay lazy.
from __future__ import annotations

from sqlalchemy import and_, case, delete, false, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.domains.transactions.models import Transaction, TransactionType
from app.domains.wallets.models import Wallet, WalletScope, WalletVisibility

# A signed-amount expression for a wallet's balance: +amount for money coming in
# (income or a transfer into this wallet), -amount for money going out (expense or
# a transfer out of this wallet).
_SIGNED_AMOUNT = case(
    (
        Transaction.type.in_(
            [TransactionType.INCOME.value, TransactionType.TRANSFER_IN.value]
        ),
        Transaction.amount,
    ),
    else_=-Transaction.amount,
)


def visibility_clause(
    family_id: int | None, user_id: int, scope: str
) -> ColumnElement[bool]:
    """The WHERE clause for wallets the caller may see under ``scope``.

    - ``family``  → shared wallets of ``family_id`` (none when it's ``None``).
    - ``personal``→ the caller's own personal wallets (independent of any family).
    - ``all``     → shared wallets plus the caller's own personal wallets.

    A personal wallet owned by someone else is never matched. Personal wallets are
    owned by ``owner_user_id`` and don't depend on a family, so a user with no
    family still sees their personal wallets.
    """
    family_only: ColumnElement[bool] = (
        and_(
            Wallet.family_id == family_id,
            Wallet.visibility == WalletVisibility.FAMILY.value,
        )
        if family_id is not None
        else false()
    )
    own_personal = and_(
        Wallet.visibility == WalletVisibility.PERSONAL.value,
        Wallet.owner_user_id == user_id,
    )
    if scope == WalletScope.FAMILY.value:
        return family_only
    if scope == WalletScope.PERSONAL.value:
        return own_personal
    return or_(family_only, own_personal)


class WalletRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        family_id: int | None,
        name: str,
        visibility: str = WalletVisibility.FAMILY.value,
        owner_user_id: int | None = None,
        icon: str | None = None,
        color: str | None = None,
    ) -> Wallet:
        wallet = Wallet(
            family_id=family_id,
            name=name,
            visibility=visibility,
            owner_user_id=owner_user_id,
            icon=icon,
            color=color,
        )
        self._session.add(wallet)
        self._session.flush()
        return wallet

    def list(self, family_id: int | None, user_id: int, scope: str) -> list[Wallet]:
        stmt = (
            select(Wallet)
            .where(visibility_clause(family_id, user_id, scope))
            .order_by(Wallet.created_at)
        )
        return list(self._session.scalars(stmt).all())

    def visible_wallet_ids(
        self, family_id: int | None, user_id: int, scope: str
    ) -> list[int]:
        """The ids of wallets the caller may see — used to scope transaction,
        balance, and statistics queries to those wallets."""
        stmt = select(Wallet.id).where(visibility_clause(family_id, user_id, scope))
        return list(self._session.scalars(stmt).all())

    def get_visible_by_rid(
        self, family_id: int | None, user_id: int, rid: str
    ) -> Wallet | None:
        """A wallet by rid, but only if the caller is allowed to see it
        (returns None for another member's personal wallet — no existence leak)."""
        stmt = select(Wallet).where(
            visibility_clause(family_id, user_id, WalletScope.ALL.value),
            Wallet.rid == rid,
        )
        return self._session.scalar(stmt)

    def balances_by_wallet(self, wallet_ids: list[int]) -> dict[int, int]:
        """Net balance per wallet_id, restricted to ``wallet_ids`` (which already
        encode visibility, so no family filter is needed). Wallets with no
        transactions are absent (→ 0)."""
        if not wallet_ids:
            return {}
        stmt = (
            select(Transaction.wallet_id, func.sum(_SIGNED_AMOUNT))
            .where(Transaction.wallet_id.in_(wallet_ids))
            .group_by(Transaction.wallet_id)
        )
        return {wallet_id: int(total) for wallet_id, total in self._session.execute(stmt)}

    def balance(self, wallet_id: int) -> int:
        stmt = select(func.coalesce(func.sum(_SIGNED_AMOUNT), 0)).where(
            Transaction.wallet_id == wallet_id,
        )
        return int(self._session.scalar(stmt) or 0)

    def counts_by_wallet(self, wallet_ids: list[int]) -> dict[int, int]:
        """Transaction count per wallet_id, restricted to ``wallet_ids`` (absent → 0)."""
        if not wallet_ids:
            return {}
        stmt = (
            select(Transaction.wallet_id, func.count())
            .where(Transaction.wallet_id.in_(wallet_ids))
            .group_by(Transaction.wallet_id)
        )
        return {wallet_id: int(n) for wallet_id, n in self._session.execute(stmt)}

    def delete_with_transactions(self, wallet_id: int) -> int:
        """Delete the wallet's transactions then the wallet (the wallet was already
        permission-checked by the caller). Returns the number of transactions
        removed. Caller commits."""
        deleted = self._session.execute(
            delete(Transaction).where(Transaction.wallet_id == wallet_id)
        ).rowcount
        self._session.execute(delete(Wallet).where(Wallet.id == wallet_id))
        return int(deleted or 0)
