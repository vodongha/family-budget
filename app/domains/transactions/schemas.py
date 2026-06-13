"""Pydantic DTOs for transactions."""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.domains.categories.schemas import CategoryRead
from app.domains.transactions.models import TransactionType


class TransactionCreate(BaseModel):
    wallet_rid: str
    type: TransactionType
    # Positive integer minor units (đồng). Direction comes from `type`, not the sign.
    amount: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=500)
    # Optional category (must belong to the family); null = uncategorized.
    category_rid: str | None = None
    # Defaults to today (server-side) when omitted.
    occurred_on: date | None = None


class TransactionRead(BaseModel):
    rid: str
    wallet_rid: str
    type: TransactionType
    amount: int
    note: str | None
    occurred_on: date
    category: CategoryRead | None
    created_at: datetime
