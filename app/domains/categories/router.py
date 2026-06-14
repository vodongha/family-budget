"""Category routes — family-scoped CRUD. Any member can manage categories."""

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import CurrentFamily, SessionDep
from app.domains.categories.schemas import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
)
from app.domains.categories.service import CategoryNotFoundError, CategoryService

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead], summary="List categories")
def list_categories(
    session: SessionDep,
    family_id: CurrentFamily,
    include_archived: bool = Query(default=False),
) -> list[CategoryRead]:
    """Your family's categories. Set `include_archived=true` to include archived
    ones."""
    categories = CategoryService(session).list(
        family_id, include_archived=include_archived
    )
    return [CategoryRead.model_validate(c) for c in categories]


@router.post(
    "",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a category",
)
def create_category(
    payload: CategoryCreate, session: SessionDep, family_id: CurrentFamily
) -> CategoryRead:
    """Add an income or expense category (name, `kind`, emoji `icon`, `color`)."""
    category = CategoryService(session).create(
        family_id, payload.name, payload.kind, payload.icon, payload.color
    )
    return CategoryRead.model_validate(category)


@router.patch("/{rid}", response_model=CategoryRead, summary="Update a category")
def update_category(
    rid: str,
    payload: CategoryUpdate,
    session: SessionDep,
    family_id: CurrentFamily,
) -> CategoryRead:
    """Partial update of a category. `404` if not in your family."""
    try:
        category = CategoryService(session).update(
            family_id, rid, payload.model_dump(exclude_unset=True)
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
    rid: str, session: SessionDep, family_id: CurrentFamily
) -> None:
    """Delete (archive) a category. `404` if not in your family."""
    try:
        CategoryService(session).delete(family_id, rid)
    except CategoryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        ) from None
