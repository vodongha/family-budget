"""Pydantic DTOs for wallet-to-wallet transfers."""

from datetime import date

from pydantic import BaseModel, Field


class TransferCreate(BaseModel):
    from_wallet_rid: str
    to_wallet_rid: str
    amount: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=500)
    occurred_on: date | None = None


class TransferRead(BaseModel):
    group_rid: str
    from_wallet_rid: str
    to_wallet_rid: str
    amount: int
    occurred_on: date
