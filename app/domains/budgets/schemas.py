"""Pydantic DTOs for budgets."""

from pydantic import BaseModel, Field

from app.domains.categories.schemas import CategoryRead


class BudgetRead(BaseModel):
    rid: str
    category: CategoryRead
    # Monthly limit (đồng) and how much of it is spent in the current month.
    amount: int
    spent: int


class BudgetCreate(BaseModel):
    category_rid: str
    amount: int = Field(gt=0)


class BudgetUpdate(BaseModel):
    amount: int = Field(gt=0)
