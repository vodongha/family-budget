"""Wallet ORM model.

A wallet holds money for a family (cash, a bank account, an e-wallet, ...). Its
balance is NEVER stored here — it is derived from the sum of its transactions
(see WalletRepository.balances_by_wallet). See the money rules in CLAUDE.md.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domains.users.models import new_rid


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    rid: Mapped[str] = mapped_column(String(26), unique=True, default=new_rid)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
