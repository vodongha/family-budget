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
        transfer_group_rid: str | None = None,
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
            transfer_group_rid=transfer_group_rid,
        )
        self._session.add(transaction)
        self._session.flush()
        return transaction

    def list_by_transfer_group(
        self, family_id: int, transfer_group_rid: str
    ) -> list[Transaction]:
        stmt = (
            select(Transaction)
            .where(
                Transaction.family_id == family_id,
                Transaction.transfer_group_rid == transfer_group_rid,
            )
            .options(selectinload(Transaction.wallet))
        )
        return list(self._session.scalars(stmt).all())

    def get_by_rid(self, family_id: int, rid: str) -> Transaction | None:
        stmt = (
            select(Transaction)
            .where(Transaction.family_id == family_id, Transaction.rid == rid)
            .options(
                selectinload(Transaction.wallet),
                selectinload(Transaction.category),
            )
        )
        return self._session.scalar(stmt)

    def delete(self, transaction: Transaction) -> None:
        self._session.delete(transaction)

    def list(
        self,
        family_id: int,
        wallet_id: int | None = None,
        wallet_ids: list[int] | None = None,
        limit: int = 100,
        type_: str | None = None,
        category_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Transaction]:
        """Transactions for the family, newest first. When ``wallet_id`` is set,
        restricts to that wallet; otherwise, when ``wallet_ids`` is given,
        restricts to that set (empty set → no rows). Optional ``type_``,
        ``category_id`` and ``date_from``/``date_to`` filters narrow the result."""
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
        if type_ is not None:
            stmt = stmt.where(Transaction.type == type_)
        if category_id is not None:
            stmt = stmt.where(Transaction.category_id == category_id)
        if date_from is not None:
            stmt = stmt.where(Transaction.occurred_on >= date_from)
        if date_to is not None:
            stmt = stmt.where(Transaction.occurred_on <= date_to)
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
