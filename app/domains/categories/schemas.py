"""Pydantic DTOs for categories."""

from pydantic import BaseModel, ConfigDict, Field

from app.domains.categories.models import CategoryKind


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rid: str
    name: str
    icon: str | None
    color: str | None
    kind: CategoryKind
    # Set for seeded defaults so the client can show a localized label.
    default_key: str | None
    is_archived: bool


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: CategoryKind
    icon: str | None = Field(default=None, max_length=16)
    color: str | None = Field(default=None, max_length=8)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    icon: str | None = Field(default=None, max_length=16)
    color: str | None = Field(default=None, max_length=8)
    is_archived: bool | None = None
