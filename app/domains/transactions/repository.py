"""DB access for transactions. Always scoped by family_id (tenant boundary)."""

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
    ) -> Transaction:
        transaction = Transaction(
            family_id=family_id,
            wallet_id=wallet_id,
            created_by_user_id=created_by_user_id,
            type=type_.value,
            amount=amount,
            note=note,
            occurred_on=occurred_on,
        )
        self._session.add(transaction)
        self._session.flush()
        return transaction

    def list(
        self, family_id: int, wallet_id: int | None = None, limit: int = 100
    ) -> list[Transaction]:
        stmt = (
            select(Transaction)
            .where(Transaction.family_id == family_id)
            .options(selectinload(Transaction.wallet))
            .order_by(Transaction.occurred_on.desc(), Transaction.id.desc())
            .limit(limit)
        )
        if wallet_id is not None:
            stmt = stmt.where(Transaction.wallet_id == wallet_id)
        return list(self._session.scalars(stmt).all())

    def family_totals(self, family_id: int) -> tuple[int, int]:
        """Return (total_income, total_expense) across the whole family."""
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
        stmt = select(income, expense).where(Transaction.family_id == family_id)
        total_income, total_expense = self._session.execute(stmt).one()
        return int(total_income), int(total_expense)
