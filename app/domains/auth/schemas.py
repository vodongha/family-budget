"""Pydantic v2 DTOs for auth — the type shield at the API boundary."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domains.users.models import UserRole


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rid: str
    email: EmailStr
    display_name: str
    phone: str | None
    family_id: int | None
    role: UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str
    family_name: str
    # Optional; validated/normalised to E.164 by the service when present.
    phone: str | None = Field(default=None, max_length=32)


class UpdateProfileRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    # Sent on every profile save (the edit form pre-fills it): a value sets/updates
    # the number, an empty value clears it.
    phone: str | None = Field(default=None, max_length=32)


class GoogleLoginRequest(BaseModel):
    id_token: str
