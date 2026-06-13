"""Category business logic — stateless; session + family_id passed in per call."""

from typing import Any

from sqlalchemy.orm import Session

from app.domains.categories.models import Category, CategoryKind
from app.domains.categories.repository import CategoryRepository


class CategoryNotFoundError(Exception):
    """Raised when a category rid does not belong to the current family."""


class CategoryService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = CategoryRepository(session)

    def list(self, family_id: int, *, include_archived: bool = False) -> list[Category]:
        return self._repo.list(family_id, include_archived=include_archived)

    def create(
        self,
        family_id: int,
        name: str,
        kind: CategoryKind,
        icon: str | None,
        color: str | None,
    ) -> Category:
        category = self._repo.add(family_id, name, icon, color, kind)
        self._session.commit()
        return category

    def update(self, family_id: int, rid: str, changes: dict[str, Any]) -> Category:
        category = self._repo.get_by_rid(family_id, rid)
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

    def delete(self, family_id: int, rid: str) -> None:
        category = self._repo.get_by_rid(family_id, rid)
        if category is None:
            raise CategoryNotFoundError(rid)
        # Transactions keep their history but become uncategorized.
        self._repo.clear_from_transactions(family_id, category.id)
        self._repo.delete(category)
        self._session.commit()
