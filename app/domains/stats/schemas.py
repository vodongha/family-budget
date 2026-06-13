"""Pydantic DTOs for statistics."""

from pydantic import BaseModel


class MonthlyPoint(BaseModel):
    month: str  # "YYYY-MM"
    income: int
    expense: int


class CategorySlice(BaseModel):
    # None for the uncategorized bucket (then default_key is "uncategorized").
    category_rid: str | None
    name: str | None
    icon: str | None
    color: str | None
    default_key: str | None
    amount: int
