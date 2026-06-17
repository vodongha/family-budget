"""DB access for budgets.

A budget is **family** (shared, ``family_id`` set) or **personal**
(``owner_user_id`` set, ``family_id`` null). Reads are scoped like wallets:
``personal`` = the caller's own, ``family`` = the family's.
"""

# A method named ``list`` shadows the builtin in the class body.
from __future__ import annotations

from datetime import date

from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.domains.budgets.models import Budget
from app.domains.transactions.models import Transaction
from app.domains.wallets.models import Wallet


def _scope_clause(
    family_id: int | None, user_id: int, scope: str
) -> ColumnElement[bool]:
    family_only: ColumnElement[bool] = (
        Budget.family_id == family_id if family_id is not None else false()
    )
    own_personal = Budget.owner_user_id == user_id
    if scope == "family":
        return family_only
    if scope == "personal":
        return own_personal
    return or_(family_only, own_personal)


class BudgetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        family_id: int | None,
        owner_user_id: int | None,
        category_id: int,
        amount: int,
        created_by_user_id: int,
    ) -> Budget:
        budget = Budget(
            family_id=family_id,
            owner_user_id=owner_user_id,
            category_id=category_id,
            amount=amount,
            created_by_user_id=created_by_user_id,
        )
        self._session.add(budget)
        self._session.flush()
        return budget

    def list(self, family_id: int | None, user_id: int, scope: str) -> list[Budget]:
        stmt = (
            select(Budget)
            .where(_scope_clause(family_id, user_id, scope))
            .options(selectinload(Budget.category))
            .order_by(Budget.created_at)
        )
        return list(self._session.scalars(stmt).all())

    def get_visible_by_rid(
        self, family_id: int | None, user_id: int, rid: str
    ) -> Budget | None:
        stmt = (
            select(Budget)
            .where(_scope_clause(family_id, user_id, "all"), Budget.rid == rid)
            .options(selectinload(Budget.category))
        )
        return self._session.scalar(stmt)

    def get_by_category(
        self, family_id: int | None, user_id: int, scope: str, category_id: int
    ) -> Budget | None:
        stmt = select(Budget).where(
            _scope_clause(family_id, user_id, scope),
            Budget.category_id == category_id,
        )
        return self._session.scalar(stmt)

    def delete(self, budget: Budget) -> None:
        self._session.delete(budget)

    def spent_by_category(
        self, wallet_ids: list[int], start: date, end: date
    ) -> list[tuple[int, str, int]]:
        """``(category_id, currency, total)`` per category and wallet currency in
        ``[start, end)`` over ``wallet_ids`` (which already encode visibility).
        Split by currency so the caller can convert each part to the base currency
        before summing. Used for current-month spending."""
        if not wallet_ids:
            return []
        stmt = (
            select(
                Transaction.category_id,
                Wallet.currency,
                func.coalesce(func.sum(Transaction.amount), 0),
            )
            .join(Wallet, Transaction.wallet_id == Wallet.id)
            .where(
                Transaction.category_id.is_not(None),
                Transaction.wallet_id.in_(wallet_ids),
                Transaction.occurred_on >= start,
                Transaction.occurred_on < end,
            )
            .group_by(Transaction.category_id, Wallet.currency)
        )
        return [
            (int(category_id), currency, int(total))
            for category_id, currency, total in self._session.execute(stmt)
        ]
