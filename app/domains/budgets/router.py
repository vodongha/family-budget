"""Budget routes — monthly per-category spending limits, personal or family."""

from fastapi import APIRouter, HTTPException, Response, status

from app.core.deps import CurrentUser, OptionalFamily, SessionDep
from app.domains.budgets.models import Budget
from app.domains.budgets.schemas import BudgetCreate, BudgetRead, BudgetUpdate
from app.domains.budgets.service import (
    BudgetFamilyRequiredError,
    BudgetNotFoundError,
    BudgetService,
    DuplicateBudgetError,
)
from app.domains.categories.schemas import CategoryRead
from app.domains.categories.service import CategoryNotFoundError
from app.domains.wallets.models import WalletScope

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _to_read(budget: Budget, spent: int) -> BudgetRead:
    return BudgetRead(
        rid=budget.rid,
        category=CategoryRead.model_validate(budget.category),
        amount=budget.amount,
        spent=spent,
    )


@router.get("", response_model=list[BudgetRead], summary="List budgets")
def list_budgets(
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
    scope: WalletScope = WalletScope.PERSONAL,
) -> list[BudgetRead]:
    """Category budgets with the current month's `spent`, for the given `scope`
    (`personal` / `family`). `spent` is derived over that scope's wallets."""
    items = BudgetService(session).list_with_spent(
        family_id, current_user.id, scope.value
    )
    return [_to_read(b, spent) for b, spent in items]


@router.post(
    "",
    response_model=BudgetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a budget",
)
def create_budget(
    payload: BudgetCreate,
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
    scope: WalletScope = WalletScope.PERSONAL,
) -> BudgetRead:
    """Set a monthly limit for one category in `scope` (`personal` default, or
    `family` — requires a family). `404` if the category isn't visible, `409` if
    it already has a budget in this scope."""
    try:
        budget, spent = BudgetService(session).create(
            family_id,
            current_user.id,
            scope.value,
            payload.category_rid,
            payload.amount,
        )
    except CategoryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        ) from None
    except BudgetFamilyRequiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create a family before adding a shared budget",
        ) from None
    except DuplicateBudgetError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This category already has a budget",
        ) from None
    return _to_read(budget, spent)


@router.patch("/{rid}", response_model=BudgetRead, summary="Update a budget")
def update_budget(
    rid: str,
    payload: BudgetUpdate,
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
) -> BudgetRead:
    """Change a budget's monthly `amount`. `404` if it isn't visible to you."""
    try:
        budget, spent = BudgetService(session).update(
            family_id, current_user.id, rid, payload.amount
        )
    except BudgetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found"
        ) from None
    return _to_read(budget, spent)


@router.delete(
    "/{rid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a budget",
)
def delete_budget(
    rid: str,
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
) -> Response:
    """Remove a category's budget. `404` if it isn't visible to you."""
    try:
        BudgetService(session).delete(family_id, current_user.id, rid)
    except BudgetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found"
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
