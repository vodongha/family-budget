"""Category business logic — stateless. Categories are personal (owned by the
user) or family (shared); the personal space works without a family."""

from typing import Any

from sqlalchemy.orm import Session

from app.domains.categories.models import Category, CategoryKind
from app.domains.categories.repository import CategoryRepository


class CategoryNotFoundError(Exception):
    """Raised when a category rid is not visible to the caller."""


class CategoryFamilyRequiredError(Exception):
    """Raised when creating a family (shared) category without a family."""


class CategoryService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = CategoryRepository(session)

    def list(
        self,
        family_id: int | None,
        user_id: int,
        scope: str = "all",
        *,
        include_archived: bool = False,
    ) -> list[Category]:
        return self._repo.list(
            family_id, user_id, scope, include_archived=include_archived
        )

    def create(
        self,
        family_id: int | None,
        user_id: int,
        scope: str,
        name: str,
        kind: CategoryKind,
        icon: str | None,
        color: str | None,
    ) -> Category:
        if scope == "family":
            if family_id is None:
                raise CategoryFamilyRequiredError()
            owner_user_id: int | None = None
            cat_family_id: int | None = family_id
        else:
            owner_user_id = user_id
            cat_family_id = None
        category = self._repo.add(
            cat_family_id, owner_user_id, name, icon, color, kind
        )
        self._session.commit()
        return category

    def update(
        self, family_id: int | None, user_id: int, rid: str, changes: dict[str, Any]
    ) -> Category:
        category = self._repo.get_visible_by_rid(family_id, user_id, rid)
        if category is None:
            raise CategoryNotFoundError(rid)
        # Renaming a seeded default makes it a custom category (drop the i18n key).
        if "name" in changes and changes["name"] != category.name:
            category.default_key = None
        for field in ("name", "icon", "color", "is_archived"):
            if field in changes:
                setattr(category, field, changes[field])
        self._session.commit()
        self._session.refresh(category)
        return category

    def delete(self, family_id: int | None, user_id: int, rid: str) -> None:
        category = self._repo.get_visible_by_rid(family_id, user_id, rid)
        if category is None:
            raise CategoryNotFoundError(rid)
        # Transactions keep their history but become uncategorized.
        self._repo.clear_from_transactions(category.id)
        self._repo.delete(category)
        self._session.commit()
