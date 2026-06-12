"""Pydantic DTOs for invitations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domains.invitations.models import InvitationStatus
from app.domains.users.models import UserRole


class InvitationCreate(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.MEMBER


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rid: str
    email: EmailStr
    role: UserRole
    status: InvitationStatus
    # The accept token — shown to the owner so they can pass the invite link along.
    token: str
    created_at: datetime


class AcceptInvitation(BaseModel):
    token: str
    password: str
    display_name: str = Field(min_length=1, max_length=120)
