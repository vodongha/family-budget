"""Pydantic DTOs for invitations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.domains.invitations.models import InvitationStatus
from app.domains.users.models import UserRole


class InvitationCreate(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    role: UserRole = UserRole.MEMBER

    @model_validator(mode="after")
    def _require_contact(self) -> "InvitationCreate":
        if not self.email and not (self.phone and self.phone.strip()):
            raise ValueError("Provide an email or a phone number")
        return self


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rid: str
    email: EmailStr | None
    phone: str | None
    role: UserRole
    status: InvitationStatus
    # The accept token — shown to the owner so they can pass the invite link along.
    token: str
    created_at: datetime


class InvitationPublic(BaseModel):
    """Safe, unauthenticated view shown on the invite landing page."""

    family_name: str
    role: UserRole
    status: InvitationStatus
    # When the invite already carries an email, the invitee doesn't enter one.
    email: EmailStr | None


class AcceptInvitation(BaseModel):
    token: str
    password: str
    display_name: str = Field(min_length=1, max_length=120)
    # Required only for phone-only invites (which carry no email).
    email: EmailStr | None = None
