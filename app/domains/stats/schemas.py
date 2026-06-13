"""Pydantic DTOs for statistics."""

from pydantic import BaseModel


class MonthlyPoint(BaseModel):
    month: str  # "YYYY-MM"
    income: int
    expense: int
