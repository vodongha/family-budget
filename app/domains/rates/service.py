"""Currency conversion — loads the stored rates once and converts amounts to base.

Construct one per request/aggregation: it snapshots the rate table so converting
many wallet balances doesn't re-query. Amounts are integer minor units of their
own currency; conversion yields integer minor units of the base currency (VND).
"""

from sqlalchemy.orm import Session

from app.core.currency import BASE_CURRENCY, convert_minor
from app.domains.rates.repository import RateRepository


class CurrencyConverter:
    def __init__(self, session: Session) -> None:
        self._rates = RateRepository(session).all_rates()

    def to_base(self, amount_minor: int, currency: str) -> int:
        """Convert minor units of ``currency`` to base-currency minor units.

        The base currency converts as-is; an unknown currency with no stored rate
        is treated as the base (rate 1) — a safe fallback so a total is never
        silently dropped (it just isn't converted)."""
        if currency == BASE_CURRENCY:
            return amount_minor
        rate = self._rates.get(currency)
        if rate is None:
            return amount_minor
        return convert_minor(amount_minor, currency, rate)
