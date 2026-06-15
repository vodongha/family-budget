"""Category routes — personal or family CRUD. Any member can manage the family's
categories; a user manages their own personal categories (no family needed)."""

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import CurrentUser, OptionalFamily, SessionDep
from app.domains.categories.schemas import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
)
from app.domains.categories.service import (
    CategoryFamilyRequiredError,
    CategoryNotFoundError,
    CategoryService,
)
from app.domains.wallets.models import WalletScope

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead], summary="List categories")
def list_categories(
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
    scope: WalletScope = WalletScope.ALL,
    include_archived: bool = Query(default=False),
) -> list[CategoryRead]:
    """Categories visible to you. `scope`: `all` (family + your personal),
    `family`, or `personal`. Set `include_archived=true` to include archived
    ones."""
    categories = CategoryService(session).list(
        family_id,
        current_user.id,
        scope.value,
        include_archived=include_archived,
    )
    return [CategoryRead.model_validate(c) for c in categories]


@router.post(
    "",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a category",
)
def create_category(
    payload: CategoryCreate,
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
    scope: WalletScope = WalletScope.PERSONAL,
) -> CategoryRead:
    """Add an income or expense category (name, `kind`, emoji `icon`, `color`).
    `scope=personal` (default) makes it private; `scope=family` makes it shared
    (requires a family — `400` otherwise)."""
    try:
        category = CategoryService(session).create(
            family_id,
            current_user.id,
            scope.value,
            payload.name,
            payload.kind,
            payload.icon,
            payload.color,
        )
    except CategoryFamilyRequiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create a family before adding a shared category",
        ) from None
    return CategoryRead.model_validate(category)


@router.patch("/{rid}", response_model=CategoryRead, summary="Update a category")
def update_category(
    rid: str,
    payload: CategoryUpdate,
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
) -> CategoryRead:
    """Partial update of a category. `404` if it isn't visible to you."""
    try:
        category = CategoryService(session).update(
            family_id, current_user.id, rid, payload.model_dump(exclude_unset=True)
        )
    except CategoryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        ) from None
    return CategoryRead.model_validate(category)


@router.delete(
    "/{rid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a category",
)
def delete_category(
    rid: str,
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
) -> None:
    """Delete a category. `404` if it isn't visible to you."""
    try:
        CategoryService(session).delete(family_id, current_user.id, rid)
    except CategoryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        ) from None
