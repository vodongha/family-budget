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
    # True once the user belongs to a family; the app uses it to route a brand-new
    # account to the "create or join a family" onboarding step.
    has_family: bool
    # True when a password is set. False for Google-only accounts, which see a
    # "set password" form (no current password) instead of "change password".
    has_password: bool
    role: UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str
    # Optional: when supplied, a family is created and the registrant owns it
    # (a convenience path / back-compat). When omitted, the account starts with
    # no family — it creates or joins one after first login (POST /families).
    family_name: str | None = Field(default=None, max_length=120)
    # Optional; validated/normalised to E.164 by the service when present.
    phone: str | None = Field(default=None, max_length=32)


class ChangePasswordRequest(BaseModel):
    # Required to change an existing password; omitted when a Google-only account
    # sets its first password.
    current_password: str | None = None
    new_password: str = Field(min_length=8, max_length=128)


class UpdateProfileRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    # Sent on every profile save (the edit form pre-fills it): a value sets/updates
    # the number, an empty value clears it.
    phone: str | None = Field(default=None, max_length=32)


class GoogleLoginRequest(BaseModel):
    id_token: str
