"""DB access for statistics — read-only, family-scoped."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.transactions.models import Transaction


class StatsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def rows_since(
        self, family_id: int, start: date
    ) -> list[tuple[date, str, int]]:
        """(occurred_on, type, amount) for the family from ``start`` onward.

        Aggregation into month buckets happens in the service (in Python) so the
        query stays portable across Oracle and the SQLite test database.
        """
        stmt = select(
            Transaction.occurred_on, Transaction.type, Transaction.amount
        ).where(
            Transaction.family_id == family_id,
            Transaction.occurred_on >= start,
        )
        return [(r[0], r[1], r[2]) for r in self._session.execute(stmt).all()]
