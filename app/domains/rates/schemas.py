"""Pydantic DTOs for exchange-rate status."""

from datetime import datetime

from pydantic import BaseModel


class RateItem(BaseModel):
    currency: str
    # Base-currency major units per 1 major unit of `currency` (e.g. USD → 25000).
    rate_to_base: float


class RatesInfo(BaseModel):
    base_currency: str
    # When the rates were last refreshed (None if never), and how many are stored.
    updated_at: datetime | None
    count: int
    # Every stored currency's rate, so a client can convert any pair (the base
    # currency is implicitly rate 1 and not listed here).
    rates: list[RateItem]
