"""Pydantic DTOs for wallets."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domains.wallets.models import WalletVisibility


class WalletCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # "family" (shared, default) or "personal" (private to the creator).
    visibility: WalletVisibility = WalletVisibility.FAMILY


class WalletDeleteResult(BaseModel):
    deleted_transactions: int


class WalletRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rid: str
    name: str
    # "family" (shared) or "personal" (private to its owner).
    visibility: WalletVisibility
    # Derived balance in integer minor units (đồng). Can be negative.
    balance: int
    # Number of transactions in this wallet (shown before a delete). Defaults to
    # 0 for callers that don't compute it (e.g. the dashboard summary).
    txn_count: int = 0
    created_at: datetime
