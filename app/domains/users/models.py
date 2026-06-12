"""User and Family ORM models.

Identifier convention: numeric ``id`` PK for joins + ``rid`` (ULID, VARCHAR2(26))
for anything exposed externally (URLs, JWT subject).
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Identity, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ulid import ULID

from app.core.database import Base


def new_rid() -> str:
    return str(ULID())


class UserRole(enum.StrEnum):
    OWNER = "owner"   # created the family; can invite/revoke members
    MEMBER = "member"  # can record and view, but not manage membership


class Family(Base):
    __tablename__ = "families"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    rid: Mapped[str] = mapped_column(String(26), unique=True, default=new_rid)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    members: Mapped[list["User"]] = relationship(back_populates="family")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    rid: Mapped[str] = mapped_column(String(26), unique=True, default=new_rid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
    family_id: Mapped[int | None] = mapped_column(ForeignKey("families.id"))
    # Stores a UserRole value. server_default keeps pre-existing rows valid after
    # the column was added; the register flow sets OWNER for a family's creator.
    role: Mapped[str] = mapped_column(
        String(10), server_default=text("'member'"), default=UserRole.MEMBER.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    family: Mapped["Family | None"] = relationship(back_populates="members")
