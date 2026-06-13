"""Pydantic DTOs for family membership."""

from pydantic import BaseModel, ConfigDict, EmailStr

from app.domains.users.models import UserRole


class MemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rid: str
    display_name: str
    email: EmailStr
    phone: str | None
    role: UserRole


class TransferOwnershipRequest(BaseModel):
    target_rid: str
