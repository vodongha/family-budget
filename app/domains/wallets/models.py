"""Wallet ORM model.

A wallet holds money for a family (cash, a bank account, an e-wallet, ...). Its
balance is NEVER stored here — it is derived from the sum of its transactions
(see WalletRepository.balances_by_wallet). See the money rules in CLAUDE.md.

A wallet is either **family** (shared — every member sees it and its
transactions) or **personal** (private — only its ``owner_user_id`` can see it,
so personal spending stays hidden from the rest of the family). The visibility
rule is enforced in WalletRepository (the tenant boundary for wallet privacy).
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Identity, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domains.users.models import new_rid


class WalletVisibility(enum.StrEnum):
    FAMILY = "family"  # shared with every family member
    PERSONAL = "personal"  # private to owner_user_id


class WalletScope(enum.StrEnum):
    """Which wallets a request wants, from the caller's point of view."""

    ALL = "all"  # family wallets + the caller's own personal wallets
    FAMILY = "family"  # shared family wallets only
    PERSONAL = "personal"  # the caller's own personal wallets only


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    rid: Mapped[str] = mapped_column(String(26), unique=True, default=new_rid)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    # "family" (shared) or "personal" (private to owner_user_id).
    visibility: Mapped[str] = mapped_column(
        String(10),
        server_default=text("'family'"),
        default=WalletVisibility.FAMILY.value,
        nullable=False,
    )
    # Non-null only for personal wallets — the sole member who can see it.
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
