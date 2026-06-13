"""Transaction ORM model + the expense/income type enum.

Money rules (CLAUDE.md): ``amount`` is a positive integer in minor units (đồng) —
the income/expense direction is carried by ``type``, never by the sign of amount.
Balances are derived by summing these rows, scoped to ``family_id``.
"""

import enum
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domains.categories.models import Category
from app.domains.users.models import new_rid
from app.domains.wallets.models import Wallet


class TransactionType(enum.StrEnum):
    EXPENSE = "expense"
    INCOME = "income"
    # The two legs of a wallet-to-wallet transfer. They move money between the
    # family's own wallets, so they affect wallet balances but are excluded from
    # income/expense totals and statistics.
    TRANSFER_OUT = "transfer_out"  # leaves the source wallet
    TRANSFER_IN = "transfer_in"  # enters the destination wallet


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    rid: Mapped[str] = mapped_column(String(26), unique=True, default=new_rid)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Stores a TransactionType value ("expense" / "income").
    type: Mapped[str] = mapped_column(String(10))
    # Positive integer, minor units (đồng). BigInteger gives headroom for summed
    # household amounts beyond a plain 32-bit Integer.
    amount: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str | None] = mapped_column(String(500))
    occurred_on: Mapped[date] = mapped_column(Date)
    # Optional label; null = uncategorized (also after its category is deleted).
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), index=True, nullable=True
    )
    # Set on the two legs of a wallet-to-wallet transfer; both legs share this
    # ULID so the pair can be read and deleted together. Null for normal txns.
    transfer_group_rid: Mapped[str | None] = mapped_column(
        String(26), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    wallet: Mapped[Wallet] = relationship()
    category: Mapped[Category | None] = relationship()
