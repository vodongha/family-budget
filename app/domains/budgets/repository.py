"""DB access for budgets. Always scoped by family_id (tenant boundary)."""

# A method named ``list`` shadows the builtin in the class body.
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domains.budgets.models import Budget
from app.domains.transactions.models import Transaction


class BudgetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self, family_id: int, category_id: int, amount: int, created_by_user_id: int
    ) -> Budget:
        budget = Budget(
            family_id=family_id,
            category_id=category_id,
            amount=amount,
            created_by_user_id=created_by_user_id,
        )
        self._session.add(budget)
        self._session.flush()
        return budget

    def list(self, family_id: int) -> list[Budget]:
        stmt = (
            select(Budget)
            .where(Budget.family_id == family_id)
            .options(selectinload(Budget.category))
            .order_by(Budget.created_at)
        )
        return list(self._session.scalars(stmt).all())

    def get_by_rid(self, family_id: int, rid: str) -> Budget | None:
        stmt = (
            select(Budget)
            .where(Budget.family_id == family_id, Budget.rid == rid)
            .options(selectinload(Budget.category))
        )
        return self._session.scalar(stmt)

    def get_by_category(self, family_id: int, category_id: int) -> Budget | None:
        stmt = select(Budget).where(
            Budget.family_id == family_id, Budget.category_id == category_id
        )
        return self._session.scalar(stmt)

    def delete(self, budget: Budget) -> None:
        self._session.delete(budget)

    def spent_by_category(
        self, family_id: int, wallet_ids: list[int], start: date, end: date
    ) -> dict[int, int]:
        """Total transacted per category in ``[start, end)`` over ``wallet_ids``.

        Used to compute current-month spending against each budget.
        """
        if not wallet_ids:
            return {}
        stmt = (
            select(Transaction.category_id, func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                Transaction.family_id == family_id,
                Transaction.category_id.is_not(None),
                Transaction.wallet_id.in_(wallet_ids),
                Transaction.occurred_on >= start,
                Transaction.occurred_on < end,
            )
            .group_by(Transaction.category_id)
        )
        return {
            int(category_id): int(total)
            for category_id, total in self._session.execute(stmt)
        }
