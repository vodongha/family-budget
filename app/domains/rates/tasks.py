"""Refresh exchange rates from a free public source.

Uses open.er-api.com (no API key, includes VND). Fetches the latest rates with
the base currency as the request base, then stores, for each supported currency,
how many base units equal one unit of that currency (the inverse of the returned
"per 1 base" figure).
"""

import json
import urllib.request

from sqlalchemy.orm import Session

from app.core.currency import BASE_CURRENCY, SUPPORTED_CURRENCIES
from app.domains.rates.repository import RateRepository

_URL = f"https://open.er-api.com/v6/latest/{BASE_CURRENCY}"


def fetch_exchange_rates(session: Session) -> int:
    """Pull the latest rates and upsert them. Returns the number updated."""
    with urllib.request.urlopen(_URL, timeout=20) as resp:  # noqa: S310
        data = json.loads(resp.read().decode())
    # ``rates[CODE]`` = how many CODE units equal one base unit; we store the
    # inverse (base units per one CODE unit).
    rates = data.get("rates") or {}
    repo = RateRepository(session)
    updated = 0
    for code in SUPPORTED_CURRENCIES:
        if code == BASE_CURRENCY:
            continue
        per_base = rates.get(code)
        if not per_base:
            continue
        repo.upsert(code, 1.0 / float(per_base))
        updated += 1
    session.commit()
    return updated
