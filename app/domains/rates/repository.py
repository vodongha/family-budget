"""DB access for exchange rates."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.rates.models import ExchangeRate


class RateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def all_rates(self) -> dict[str, float]:
        """``{currency: rate_to_base}`` for every stored currency."""
        rows = self._session.scalars(select(ExchangeRate)).all()
        return {r.currency: r.rate_to_base for r in rows}

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
