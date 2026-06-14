"""User and Family ORM models.

Identifier convention: numeric ``id`` PK for joins + ``rid`` (ULID, VARCHAR2(26))
for anything exposed externally (URLs, JWT subject).
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, String, func, text
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
    # Soft delete: set when the sole owner deletes their account; a scheduled job
    # hard-purges the family (and all its data) once deleted_at is older than the
    # retention window. See app.domains.account.service.
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, server_default=text("0"), default=False, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    members: Mapped[list["User"]] = relationship(back_populates="family")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    rid: Mapped[str] = mapped_column(String(26), unique=True, default=new_rid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Empty for Google-only accounts (they authenticate via google_sub, not a password).
    hashed_password: Mapped[str] = mapped_column(String(255))
    # Google account subject id when linked; cleared on account deletion (unlink).
    google_sub: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    display_name: Mapped[str] = mapped_column(String(120))
    # Optional contact number, stored canonically in E.164 (e.g. +84912345678).
    # Unique when present (nullable columns allow many NULLs), so it can be used
    # to invite an existing account into a family.
    phone: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True
    )
    family_id: Mapped[int | None] = mapped_column(ForeignKey("families.id"))
    # Stores a UserRole value. server_default keeps pre-existing rows valid after
    # the column was added; the register flow sets OWNER for a family's creator.
    role: Mapped[str] = mapped_column(
        String(10), server_default=text("'member'"), default=UserRole.MEMBER.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Soft delete (Google Play account-deletion policy): set on self-deletion;
    # login and token validation reject deleted users immediately. A scheduled
    # job purges (families) or anonymises (members) once past the retention window.
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, server_default=text("0"), default=False, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    family: Mapped["Family | None"] = relationship(back_populates="members")

    @property
    def has_family(self) -> bool:
        """Whether the user belongs to a family yet. A freshly registered (or new
        Google) account has none until they create or join one."""
        return self.family_id is not None

    @property
    def has_password(self) -> bool:
        """Whether a password is set. Google-only accounts have none until they
        set one (then they can also sign in with email + password)."""
        return bool(self.hashed_password)
