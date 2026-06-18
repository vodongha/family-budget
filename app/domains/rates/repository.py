"""DB access for exchange rates."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.rates.models import ExchangeRate


class RateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def all_rates(self) -> dict[str, float]:
        """``{currency: rate_to_base}`` for every stored currency."""
        rows = self._session.scalars(select(ExchangeRate)).all()
        return {r.currency: r.rate_to_base for r in rows}

    def latest_updated_at(self) -> datetime | None:
        """The most recent ``updated_at`` across all rates (when they were last
        refreshed), or ``None`` if none are stored yet."""
        return self._session.scalar(select(func.max(ExchangeRate.updated_at)))

    def count(self) -> int:
        """How many non-base currencies have a stored rate."""
        return (
            self._session.scalar(select(func.count()).select_from(ExchangeRate))
            or 0
        )

    def upsert(self, currency: str, rate_to_base: float) -> None:
        existing = self._session.scalar(
            select(ExchangeRate).where(ExchangeRate.currency == currency)
        )
        if existing is None:
            self._session.add(
                ExchangeRate(currency=currency, rate_to_base=rate_to_base)
            )
        else:
            existing.rate_to_base = rate_to_base
            existing.updated_at = datetime.now(UTC).replace(tzinfo=None)
