"""Currency conversion — loads the stored rates once and converts amounts to base.

Construct one per request/aggregation: it snapshots the rate table so converting
many wallet balances doesn't re-query. Amounts are integer minor units of their
own currency; conversion yields integer minor units of the base currency (VND).
"""

from sqlalchemy.orm import Session

from app.core.currency import (
    BASE_CURRENCY,
    convert_from_base,
    convert_minor,
    is_supported,
)
from app.domains.rates.repository import RateRepository


class CurrencyConverter:
    """Converts amounts to the base currency, and base-currency totals into a
    chosen display ``target``. Construct one per request/aggregation: it snapshots
    the rate table once."""

    def __init__(self, session: Session, target: str = BASE_CURRENCY) -> None:
        self._rates = RateRepository(session).all_rates()
        # An unsupported target degrades to the base currency rather than failing.
        self._target = target if is_supported(target) else BASE_CURRENCY

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

    def base_to_target(self, base_minor: int) -> int:
        """Convert base-currency minor units into the configured display target.

        Target == base passes through; a target with no stored rate falls back to
        base (the figure stays meaningful, just unconverted)."""
        if self._target == BASE_CURRENCY:
            return base_minor
        rate = self._rates.get(self._target)
        if rate is None:
            return base_minor
        return convert_from_base(base_minor, self._target, rate)
