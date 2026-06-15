"""Pydantic DTOs for wallets."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domains.wallets.models import WalletVisibility


class WalletCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # "family" (shared, default) or "personal" (private to the creator).
    visibility: WalletVisibility = WalletVisibility.FAMILY
    icon: str | None = Field(default=None, max_length=32)
    color: str | None = Field(default=None, max_length=16)


class WalletUpdate(BaseModel):
    """Editable wallet fields. Only the provided fields change; visibility is
    immutable (changing it would move data across the privacy boundary)."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    icon: str | None = Field(default=None, max_length=32)
    color: str | None = Field(default=None, max_length=16)


class WalletDeleteResult(BaseModel):
    deleted_transactions: int


class WalletRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rid: str
    name: str
    icon: str | None = None
    color: str | None = None
    # "family" (shared) or "personal" (private to its owner).
    visibility: WalletVisibility
    # Derived balance in integer minor units (đồng). Can be negative.
    balance: int
    # Number of transactions in this wallet (shown before a delete). Defaults to
    # 0 for callers that don't compute it (e.g. the dashboard summary).
    txn_count: int = 0
    # True when the caller created this wallet — lets the client show edit/delete
    # for a shared wallet to its creator, not only the family owner.
    created_by_me: bool = False
    created_at: datetime
