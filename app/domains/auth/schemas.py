"""Pydantic v2 DTOs for auth — the type shield at the API boundary."""

from pydantic import BaseModel, ConfigDict, EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rid: str
    email: EmailStr
    display_name: str
    family_id: int | None


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str
    family_name: str
