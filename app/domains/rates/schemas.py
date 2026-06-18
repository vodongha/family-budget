"""Pydantic DTOs for exchange-rate status."""

from datetime import datetime

from pydantic import BaseModel


class RatesInfo(BaseModel):
    base_currency: str
    # When the rates were last refreshed (None if never), and how many are stored.
    updated_at: datetime | None
    count: int
