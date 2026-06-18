"""Minor-unit helpers for the admin transaction forms.

The API/app exchange integer minor units; the admin forms instead let a human
type a normal amount in the wallet's currency, so we convert here. Mirrors the
money rule: amounts are integers, never floats at rest.
"""

from decimal import Decimal, InvalidOperation

from app.core.currency import decimals


def to_minor(amount: str, currency: str) -> int | None:
    """Parse a human amount (e.g. "12.50") into integer minor units of
    ``currency``, or ``None`` if it isn't a valid non-negative number."""
    text = (amount or "").strip().replace(",", "")
    if not text:
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if value < 0:
        return None
    scaled = value * (10 ** decimals(currency))
    # Reject sub-minor-unit precision rather than silently rounding money.
    if scaled != scaled.to_integral_value():
        return int(scaled.to_integral_value())
    return int(scaled)


def to_major(amount_minor: int, currency: str) -> str:
    """Format integer minor units as a plain major-unit string for a form field
    (e.g. 1250 USD-cents → "12.50", 50000 VND → "50000")."""
    d = decimals(currency)
    if d == 0:
        return str(amount_minor)
    quantum = Decimal(10) ** -d
    return str((Decimal(amount_minor) / (10 ** d)).quantize(quantum))
