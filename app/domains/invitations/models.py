"""Invitation ORM model + status enum.

An owner invites someone by email to join their family. The invitee accepts with
the secret ``token`` (plus a chosen password), which creates their user account in
that family with the granted role.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domains.users.models import new_rid


class InvitationStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    rid: Mapped[str] = mapped_column(String(26), unique=True, default=new_rid)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(10))  # UserRole value to grant
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(10))  # InvitationStatus value
    invited_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
