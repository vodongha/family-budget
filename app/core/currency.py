"""Currency support: the set of currencies we handle and how to convert.

Money is stored as integer **minor units of each wallet's own currency** (VND has
0 decimals, so a minor unit is 1 đồng; USD has 2, so a minor unit is 1 cent).
Totals that span wallets are converted to a single **base currency** (VND) using
the latest stored exchange rate, so a dashboard/stat figure never sums raw minor
units of different currencies.
"""

from __future__ import annotations

# ISO-4217 code -> number of decimal places (minor units per major unit = 10**dp).
SUPPORTED_CURRENCIES: dict[str, int] = {
    "VND": 0,
    "USD": 2,
    "EUR": 2,
    "JPY": 0,
    "GBP": 2,
    "AUD": 2,
    "SGD": 2,
    "KRW": 0,
    "CNY": 2,
    "THB": 2,
}

# Everything aggregates into this currency for cross-wallet totals.
BASE_CURRENCY = "VND"


def is_supported(code: str) -> bool:
    return code in SUPPORTED_CURRENCIES


def decimals(code: str) -> int:
    return SUPPORTED_CURRENCIES.get(code, 0)


def convert_minor(
    amount_minor: int, from_code: str, rate_to_base: float
) -> int:
    """Convert ``amount_minor`` (minor units of ``from_code``) into base-currency
    minor units, given ``rate_to_base`` = how many BASE major units equal one
    major unit of ``from_code``.

    Example: 1050 USD-minor (= $10.50) with rate 25000 → 10.50 * 25000 = 262500
    VND (VND has 0 decimals, so 262500 minor = 262500 đồng).
    """
    if from_code == BASE_CURRENCY:
        return amount_minor
    major = amount_minor / (10 ** decimals(from_code))
    base_major = major * rate_to_base
    return round(base_major * (10 ** decimals(BASE_CURRENCY)))
