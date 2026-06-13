"""DB access for transactions. Always scoped by family_id (tenant boundary)."""

# A method named ``list`` shadows the builtin in the class body, so ``list[int]``
# annotations on later methods must stay lazy.
from __future__ import annotations

from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from app.domains.transactions.models import Transaction, TransactionType


class TransactionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        family_id: int,
        wallet_id: int,
        created_by_user_id: int,
        type_: TransactionType,
        amount: int,
        note: str | None,
        occurred_on: date,
        category_id: int | None = None,
    ) -> Transaction:
        transaction = Transaction(
            family_id=family_id,
            wallet_id=wallet_id,
            created_by_user_id=created_by_user_id,
            type=type_.value,
            amount=amount,
            note=note,
            occurred_on=occurred_on,
            category_id=category_id,
        )
        self._session.add(transaction)
        self._session.flush()
        return transaction

    def list(
        self,
        family_id: int,
        wallet_id: int | None = None,
        wallet_ids: list[int] | None = None,
        limit: int = 100,
    ) -> list[Transaction]:
        """Transactions for the family, newest first. When ``wallet_id`` is set,
        restricts to that wallet; otherwise, when ``wallet_ids`` is given,
        restricts to that set (empty set → no rows)."""
        if wallet_ids is not None and not wallet_ids:
            return []
        stmt = (
            select(Transaction)
            .where(Transaction.family_id == family_id)
            .options(
                selectinload(Transaction.wallet),
                selectinload(Transaction.category),
            )
            .order_by(Transaction.occurred_on.desc(), Transaction.id.desc())
            .limit(limit)
        )
        if wallet_id is not None:
            stmt = stmt.where(Transaction.wallet_id == wallet_id)
        elif wallet_ids is not None:
            stmt = stmt.where(Transaction.wallet_id.in_(wallet_ids))
        return list(self._session.scalars(stmt).all())

    def family_totals(
        self, family_id: int, wallet_ids: list[int]
    ) -> tuple[int, int]:
        """Return (total_income, total_expense) over the given wallets."""
        if not wallet_ids:
            return 0, 0
        income = func.coalesce(
            func.sum(
                case(
                    (Transaction.type == TransactionType.INCOME.value, Transaction.amount),
                    else_=0,
                )
            ),
            0,
        )
        expense = func.coalesce(
            func.sum(
                case(
                    (Transaction.type == TransactionType.EXPENSE.value, Transaction.amount),
                    else_=0,
                )
            ),
            0,
        )
        stmt = select(income, expense).where(
            Transaction.family_id == family_id,
            Transaction.wallet_id.in_(wallet_ids),
        )
        total_income, total_expense = self._session.execute(stmt).one()
        return int(total_income), int(total_expense)
