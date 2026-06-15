"""Budget ORM model.

A budget is a **monthly spending limit for a category**, shared at the family
level. Spending against it is derived from the category's transactions in the
current month (never stored). One budget per category per family.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domains.categories.models import Category
from app.domains.users.models import new_rid


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("family_id", "category_id", name="uq_budget_family_category"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    rid: Mapped[str] = mapped_column(String(26), unique=True, default=new_rid)
    # Family (shared, family_id set) or personal (owner_user_id set, family_id
    # null) — a budget limits spending on a family or a personal category.
    family_id: Mapped[int | None] = mapped_column(
        ForeignKey("families.id"), index=True, nullable=True
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"), index=True
    )
    # Monthly limit, minor units (đồng). BigInteger for headroom.
    amount: Mapped[int] = mapped_column(BigInteger)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    category: Mapped[Category] = relationship()
