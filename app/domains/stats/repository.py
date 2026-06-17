"""DB access for statistics — read-only, family-scoped."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.categories.models import Category
from app.domains.transactions.models import Transaction
from app.domains.wallets.models import Wallet


class CategoryRow:
    """One transaction row carrying its (optional) category's display metadata.

    ``category_rid`` is ``None`` for uncategorized transactions. ``currency`` is
    the row's wallet currency, so the service can convert ``amount`` to base.
    """

    def __init__(
        self,
        type: str,
        amount: int,
        currency: str,
        category_rid: str | None,
        name: str | None,
        icon: str | None,
        color: str | None,
        default_key: str | None,
    ) -> None:
        self.type = type
        self.amount = amount
        self.currency = currency
        self.category_rid = category_rid
        self.name = name
        self.icon = icon
        self.color = color
        self.default_key = default_key


class StatsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def rows_since(
        self, start: date, wallet_ids: list[int]
    ) -> list[tuple[date, str, int, str]]:
        """(occurred_on, type, amount, currency) from ``start`` onward, restricted
        to ``wallet_ids`` (which already encode visibility). ``currency`` lets the
        service convert each amount to the base currency before bucketing.

        Aggregation into month buckets happens in the service (in Python) so the
        query stays portable across Oracle and the SQLite test database.
        """
        if not wallet_ids:
            return []
        stmt = (
            select(
                Transaction.occurred_on,
                Transaction.type,
                Transaction.amount,
                Wallet.currency,
            )
            .join(Wallet, Transaction.wallet_id == Wallet.id)
            .where(
                Transaction.occurred_on >= start,
                Transaction.wallet_id.in_(wallet_ids),
            )
        )
        return [(r[0], r[1], r[2], r[3]) for r in self._session.execute(stmt).all()]

    def category_rows_since(
        self, start: date, wallet_ids: list[int]
    ) -> list[CategoryRow]:
        """Transactions from ``start`` onward (restricted to ``wallet_ids``), each
        with its category metadata.

        LEFT JOIN so uncategorized transactions are kept (category fields NULL).
        Aggregation by category happens in the service (in Python) for portability.
        """
        if not wallet_ids:
            return []
        stmt = (
            select(
                Transaction.type,
                Transaction.amount,
                Wallet.currency,
                Category.rid,
                Category.name,
                Category.icon,
                Category.color,
                Category.default_key,
            )
            .join(Wallet, Transaction.wallet_id == Wallet.id)
            .outerjoin(Category, Transaction.category_id == Category.id)
            .where(
                Transaction.occurred_on >= start,
                Transaction.wallet_id.in_(wallet_ids),
            )
        )
        return [
            CategoryRow(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7])
            for r in self._session.execute(stmt).all()
        ]
