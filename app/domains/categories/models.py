"""Category ORM model + kind enum.

Categories are family-scoped labels for transactions (Food, Transport, Salary…).
Seeded defaults carry a stable ``default_key`` so the app can show a localized
name; the key is cleared once a user renames the category (it becomes custom).
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domains.users.models import new_rid


class CategoryKind(enum.StrEnum):
    EXPENSE = "expense"
    INCOME = "income"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    rid: Mapped[str] = mapped_column(String(26), unique=True, default=new_rid)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    # An emoji shown as the category's icon (simple, cross-platform, theme-agnostic).
    icon: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Hex colour (AARRGGBB) for the category's chip/avatar; nullable.
    color: Mapped[str | None] = mapped_column(String(8), nullable=True)
    kind: Mapped[str] = mapped_column(String(10))  # CategoryKind value
    # Non-null for seeded defaults → the app localizes the label by this key.
    # Cleared when the user renames the category (then `name` is shown verbatim).
    default_key: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, server_default=text("0"), default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
