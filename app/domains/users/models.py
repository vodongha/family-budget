"""User and Family ORM models.

Identifier convention: numeric ``id`` PK for joins + ``rid`` (ULID, VARCHAR2(26))
for anything exposed externally (URLs, JWT subject).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ulid import ULID

from app.core.database import Base


def new_rid() -> str:
    return str(ULID())


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
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    family: Mapped["Family | None"] = relationship(back_populates="members")
