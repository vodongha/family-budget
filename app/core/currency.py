"""Currency support: the set of currencies we handle and how to convert.

Money is stored as integer **minor units of each wallet's own currency** (VND has
0 decimals, so a minor unit is 1 đồng; USD has 2, so a minor unit is 1 cent).
Totals that span wallets are converted to a single **base currency** (VND) using
the latest stored exchange rate, so a dashboard/stat figure never sums raw minor
units of different currencies.
"""

from __future__ import annotations

# ISO-4217 code -> number of decimal places (minor units per major unit = 10**dp).
# A broad set of the world's commonly-used currencies (all available from the rate
# source). The decimals follow ISO-4217: most are 2; a few have 0 or 3. The
# frontend (lib/src/core/money.dart) mirrors this map exactly — keep them in sync.
SUPPORTED_CURRENCIES: dict[str, int] = {
    # Zero-decimal currencies.
    "VND": 0,
    "JPY": 0,
    "KRW": 0,
    "CLP": 0,
    "ISK": 0,
    # Three-decimal currencies.
    "KWD": 3,
    "BHD": 3,
    "OMR": 3,
    "JOD": 3,
    # Two-decimal currencies (the default).
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "AUD": 2,
    "CAD": 2,
    "CHF": 2,
    "CNY": 2,
    "HKD": 2,
    "NZD": 2,
    "SGD": 2,
    "TWD": 2,
    "SEK": 2,
    "NOK": 2,
    "DKK": 2,
    "PLN": 2,
    "CZK": 2,
    "HUF": 2,
    "RON": 2,
    "BGN": 2,
    "TRY": 2,
    "RUB": 2,
    "UAH": 2,
    "THB": 2,
    "IDR": 2,
    "MYR": 2,
    "PHP": 2,
    "INR": 2,
    "PKR": 2,
    "BDT": 2,
    "LKR": 2,
    "AED": 2,
    "SAR": 2,
    "QAR": 2,
    "ILS": 2,
    "EGP": 2,
    "ZAR": 2,
    "NGN": 2,
    "KES": 2,
    "MAD": 2,
    "MXN": 2,
    "BRL": 2,
    "ARS": 2,
    "COP": 2,
    "PEN": 2,
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


def convert_from_base(base_minor: int, to_code: str, rate_to_base: float) -> int:
    """Convert ``base_minor`` (minor units of BASE) into ``to_code`` minor units,
    given ``rate_to_base`` = how many BASE major units equal one major unit of
    ``to_code``. The inverse of :func:`convert_minor`, used to render cross-wallet
    totals in a user-chosen display currency.

    Example: 262500 VND with USD rate 25000 → 262500 / 25000 = $10.50 → 1050
    USD-minor.
    """
    if to_code == BASE_CURRENCY:
        return base_minor
    base_major = base_minor / (10 ** decimals(BASE_CURRENCY))
    target_major = base_major / rate_to_base
    return round(target_major * (10 ** decimals(to_code)))
