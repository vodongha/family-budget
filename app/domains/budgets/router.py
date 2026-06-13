"""Budget routes — monthly per-category spending limits (family-level)."""

from fastapi import APIRouter, HTTPException, Response, status

from app.core.deps import CurrentFamily, CurrentUser, SessionDep
from app.domains.budgets.models import Budget
from app.domains.budgets.schemas import BudgetCreate, BudgetRead, BudgetUpdate
from app.domains.budgets.service import (
    BudgetNotFoundError,
    BudgetService,
    DuplicateBudgetError,
)
from app.domains.categories.schemas import CategoryRead
from app.domains.categories.service import CategoryNotFoundError

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _to_read(budget: Budget, spent: int) -> BudgetRead:
    return BudgetRead(
        rid=budget.rid,
        category=CategoryRead.model_validate(budget.category),
        amount=budget.amount,
        spent=spent,
    )


@router.get("", response_model=list[BudgetRead])
def list_budgets(
    session: SessionDep, family_id: CurrentFamily, current_user: CurrentUser
) -> list[BudgetRead]:
    items = BudgetService(session).list_with_spent(family_id, current_user.id)
    return [_to_read(b, spent) for b, spent in items]


@router.post("", response_model=BudgetRead, status_code=status.HTTP_201_CREATED)
def create_budget(
    payload: BudgetCreate,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> BudgetRead:
    try:
        budget, spent = BudgetService(session).create(
            family_id, current_user.id, payload.category_rid, payload.amount
        )
    except CategoryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        ) from None
    except DuplicateBudgetError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This category already has a budget",
        ) from None
    return _to_read(budget, spent)


@router.patch("/{rid}", response_model=BudgetRead)
def update_budget(
    rid: str,
    payload: BudgetUpdate,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> BudgetRead:
    try:
        budget, spent = BudgetService(session).update(
            family_id, current_user.id, rid, payload.amount
        )
    except BudgetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found"
        ) from None
    return _to_read(budget, spent)


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(
    rid: str, session: SessionDep, family_id: CurrentFamily, current_user: CurrentUser
) -> Response:
    try:
        BudgetService(session).delete(family_id, rid)
    except BudgetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found"
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
