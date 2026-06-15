"""DB access for categories.

A category is **family** (shared, ``family_id`` set) or **personal** (private,
``owner_user_id`` set, ``family_id`` null). Reads are scoped like wallets:
``personal`` = the caller's own, ``family`` = the family's, ``all`` = both.
"""

from sqlalchemy import false, or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.domains.categories.defaults import DEFAULT_CATEGORIES
from app.domains.categories.models import Category, CategoryKind
from app.domains.transactions.models import Transaction


def _scope_clause(
    family_id: int | None, user_id: int, scope: str
) -> ColumnElement[bool]:
    family_only: ColumnElement[bool] = (
        Category.family_id == family_id if family_id is not None else false()
    )
    own_personal = Category.owner_user_id == user_id
    if scope == "family":
        return family_only
    if scope == "personal":
        return own_personal
    return or_(family_only, own_personal)


class CategoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def seed_defaults(
        self, family_id: int | None = None, owner_user_id: int | None = None
    ) -> None:
        """Insert the default category set for a new family (``family_id``) or a
        new personal space (``owner_user_id``)."""
        for key, name, icon, color, kind in DEFAULT_CATEGORIES:
            self._session.add(
                Category(
                    family_id=family_id,
                    owner_user_id=owner_user_id,
                    name=name,
                    icon=icon,
                    color=color,
                    kind=kind.value,
                    default_key=key,
                )
            )

    def list(
        self,
        family_id: int | None,
        user_id: int,
        scope: str = "all",
        *,
        include_archived: bool = False,
    ) -> list[Category]:
        stmt = select(Category).where(_scope_clause(family_id, user_id, scope))
        if not include_archived:
            stmt = stmt.where(Category.is_archived == false())
        stmt = stmt.order_by(Category.kind, Category.created_at)
        return list(self._session.scalars(stmt).all())

    def get_visible_by_rid(
        self, family_id: int | None, user_id: int, rid: str
    ) -> Category | None:
        """A category by rid the caller may see (their personal one or one of
        their family's). ``None`` otherwise."""
        return self._session.scalar(
            select(Category).where(
                _scope_clause(family_id, user_id, "all"),
                Category.rid == rid,
            )
        )

    def add(
        self,
        family_id: int | None,
        owner_user_id: int | None,
        name: str,
        icon: str | None,
        color: str | None,
        kind: CategoryKind,
    ) -> Category:
        category = Category(
            family_id=family_id,
            owner_user_id=owner_user_id,
            name=name,
            icon=icon,
            color=color,
            kind=kind.value,
        )
        self._session.add(category)
        self._session.flush()
        return category

    def clear_from_transactions(self, category_id: int) -> None:
        """Detach a category from its transactions (set category_id NULL)."""
        self._session.execute(
            update(Transaction)
            .where(Transaction.category_id == category_id)
            .values(category_id=None)
        )

    def delete(self, category: Category) -> None:
        self._session.delete(category)
