"""Budget business logic — stateless. Family-level monthly category limits."""

from datetime import date

from sqlalchemy.orm import Session

from app.domains.budgets.models import Budget
from app.domains.budgets.repository import BudgetRepository
from app.domains.categories.repository import CategoryRepository
from app.domains.categories.service import CategoryNotFoundError
from app.domains.wallets.models import WalletScope
from app.domains.wallets.repository import WalletRepository


class BudgetNotFoundError(Exception):
    """Raised when a budget rid is unknown in this family."""


class DuplicateBudgetError(Exception):
    """Raised when the category already has a budget."""


def _current_month_range(today: date | None = None) -> tuple[date, date]:
    """[first day of this month, first day of next month)."""
    today = today or date.today()
    start = today.replace(day=1)
    end = (
        date(start.year + 1, 1, 1)
        if start.month == 12
        else date(start.year, start.month + 1, 1)
    )
    return start, end


class BudgetService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = BudgetRepository(session)
        self._categories = CategoryRepository(session)
        self._wallets = WalletRepository(session)

    def list_with_spent(
        self, family_id: int, user_id: int
    ) -> list[tuple[Budget, int]]:
        budgets = self._repo.list(family_id)
        # Spending is tracked over shared family wallets (personal stays private).
        wallet_ids = self._wallets.visible_wallet_ids(
            family_id, user_id, WalletScope.FAMILY.value
        )
        start, end = _current_month_range()
        spent = self._repo.spent_by_category(family_id, wallet_ids, start, end)
        return [(b, spent.get(b.category_id, 0)) for b in budgets]

    def create(
        self, family_id: int, user_id: int, category_rid: str, amount: int
    ) -> tuple[Budget, int]:
        category = self._categories.get_by_rid(family_id, category_rid)
        if category is None:
            raise CategoryNotFoundError(category_rid)
        if self._repo.get_by_category(family_id, category.id) is not None:
            raise DuplicateBudgetError(category_rid)
        self._repo.add(family_id, category.id, amount, user_id)
        self._session.commit()
        return self._spent_for(family_id, user_id, category_rid)

    def update(
        self, family_id: int, user_id: int, rid: str, amount: int
    ) -> tuple[Budget, int]:
        budget = self._repo.get_by_rid(family_id, rid)
        if budget is None:
            raise BudgetNotFoundError(rid)
        budget.amount = amount
        self._session.commit()
        self._session.refresh(budget)
        return budget, self._month_spent(family_id, user_id, budget.category_id)

    def delete(self, family_id: int, rid: str) -> None:
        budget = self._repo.get_by_rid(family_id, rid)
        if budget is None:
            raise BudgetNotFoundError(rid)
        self._repo.delete(budget)
        self._session.commit()

    def _month_spent(self, family_id: int, user_id: int, category_id: int) -> int:
        wallet_ids = self._wallets.visible_wallet_ids(
            family_id, user_id, WalletScope.FAMILY.value
        )
        start, end = _current_month_range()
        return self._repo.spent_by_category(family_id, wallet_ids, start, end).get(
            category_id, 0
        )

    def _spent_for(
        self, family_id: int, user_id: int, category_rid: str
    ) -> tuple[Budget, int]:
        # Reload with the category relationship populated for the response.
        for budget, spent in self.list_with_spent(family_id, user_id):
            if budget.category.rid == category_rid:
                return budget, spent
        raise BudgetNotFoundError(category_rid)
