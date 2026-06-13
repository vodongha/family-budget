"""DB access for categories. Always scoped by family_id (tenant boundary)."""

from sqlalchemy import false, select, update
from sqlalchemy.orm import Session

from app.domains.categories.defaults import DEFAULT_CATEGORIES
from app.domains.categories.models import Category, CategoryKind
from app.domains.transactions.models import Transaction


class CategoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def seed_defaults(self, family_id: int) -> None:
        """Insert the default category set for a freshly created family."""
        for key, name, icon, color, kind in DEFAULT_CATEGORIES:
            self._session.add(
                Category(
                    family_id=family_id,
                    name=name,
                    icon=icon,
                    color=color,
                    kind=kind.value,
                    default_key=key,
                )
            )

    def list(
        self, family_id: int, *, include_archived: bool = False
    ) -> list[Category]:
        stmt = select(Category).where(Category.family_id == family_id)
        if not include_archived:
            stmt = stmt.where(Category.is_archived == false())
        stmt = stmt.order_by(Category.kind, Category.created_at)
        return list(self._session.scalars(stmt).all())

    def get_by_rid(self, family_id: int, rid: str) -> Category | None:
        return self._session.scalar(
            select(Category).where(
                Category.family_id == family_id, Category.rid == rid
            )
        )

    def add(
        self,
        family_id: int,
        name: str,
        icon: str | None,
        color: str | None,
        kind: CategoryKind,
    ) -> Category:
        category = Category(
            family_id=family_id,
            name=name,
            icon=icon,
            color=color,
            kind=kind.value,
        )
        self._session.add(category)
        self._session.flush()
        return category

    def clear_from_transactions(self, family_id: int, category_id: int) -> None:
        """Detach a category from its transactions (set category_id NULL)."""
        self._session.execute(
            update(Transaction)
            .where(
                Transaction.family_id == family_id,
                Transaction.category_id == category_id,
            )
            .values(category_id=None)
        )

    def delete(self, category: Category) -> None:
        self._session.delete(category)
