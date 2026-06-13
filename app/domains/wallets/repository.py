"""DB access for wallets. Always scoped by family_id (tenant boundary)."""

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from app.domains.transactions.models import Transaction, TransactionType
from app.domains.wallets.models import Wallet

# A signed-amount expression: +amount for income, -amount for expense.
_SIGNED_AMOUNT = case(
    (Transaction.type == TransactionType.INCOME.value, Transaction.amount),
    else_=-Transaction.amount,
)


class WalletRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, family_id: int, name: str) -> Wallet:
        wallet = Wallet(family_id=family_id, name=name)
        self._session.add(wallet)
        self._session.flush()
        return wallet

    def list(self, family_id: int) -> list[Wallet]:
        stmt = (
            select(Wallet)
            .where(Wallet.family_id == family_id)
            .order_by(Wallet.created_at)
        )
        return list(self._session.scalars(stmt).all())

    def get_by_rid(self, family_id: int, rid: str) -> Wallet | None:
        stmt = select(Wallet).where(Wallet.family_id == family_id, Wallet.rid == rid)
        return self._session.scalar(stmt)

    def balances_by_wallet(self, family_id: int) -> dict[int, int]:
        """Net balance per wallet_id. Wallets with no transactions are absent (→ 0)."""
        stmt = (
            select(Transaction.wallet_id, func.sum(_SIGNED_AMOUNT))
            .where(Transaction.family_id == family_id)
            .group_by(Transaction.wallet_id)
        )
        return {wallet_id: int(total) for wallet_id, total in self._session.execute(stmt)}

    def balance(self, family_id: int, wallet_id: int) -> int:
        stmt = select(func.coalesce(func.sum(_SIGNED_AMOUNT), 0)).where(
            Transaction.family_id == family_id,
            Transaction.wallet_id == wallet_id,
        )
        return int(self._session.scalar(stmt) or 0)

    def counts_by_wallet(self, family_id: int) -> dict[int, int]:
        """Transaction count per wallet_id (absent → 0)."""
        stmt = (
            select(Transaction.wallet_id, func.count())
            .where(Transaction.family_id == family_id)
            .group_by(Transaction.wallet_id)
        )
        return {wallet_id: int(n) for wallet_id, n in self._session.execute(stmt)}

    def delete_with_transactions(self, family_id: int, wallet_id: int) -> int:
        """Delete the wallet's transactions then the wallet. Returns the number of
        transactions removed. Caller commits."""
        deleted = self._session.execute(
            delete(Transaction).where(
                Transaction.family_id == family_id,
                Transaction.wallet_id == wallet_id,
            )
        ).rowcount
        self._session.execute(
            delete(Wallet).where(
                Wallet.family_id == family_id, Wallet.id == wallet_id
            )
        )
        return int(deleted or 0)
