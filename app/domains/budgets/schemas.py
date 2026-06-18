"""Pydantic DTOs for budgets."""

from pydantic import BaseModel, Field

from app.domains.categories.schemas import CategoryRead


class BudgetRead(BaseModel):
    rid: str
    category: CategoryRead
    # Monthly limit and current-month spend, in minor units of the request's
    # display currency (stored in the base currency, converted on the way out).
    amount: int
    spent: int


class BudgetCreate(BaseModel):
    category_rid: str
    # In minor units of the request's display currency (converted to base on save).
    amount: int = Field(gt=0)


class BudgetUpdate(BaseModel):
    # In minor units of the request's display currency (converted to base on save).
    amount: int = Field(gt=0)
