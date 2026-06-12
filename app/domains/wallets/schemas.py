"""Pydantic DTOs for wallets."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WalletCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WalletRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rid: str
    name: str
    # Derived balance in integer minor units (đồng). Can be negative.
    balance: int
    created_at: datetime
