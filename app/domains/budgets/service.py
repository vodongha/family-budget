"""Budget business logic — stateless. Monthly per-category limits, personal or
family. Spending is derived over the wallets of the budget's scope."""

from datetime import date

from sqlalchemy.orm import Session

from app.domains.budgets.models import Budget
from app.domains.budgets.repository import BudgetRepository
from app.domains.categories.repository import CategoryRepository
from app.domains.categories.service import CategoryNotFoundError
from app.domains.rates.service import CurrencyConverter
from app.domains.wallets.repository import WalletRepository


class BudgetNotFoundError(Exception):
    """Raised when a budget rid is not visible to the caller."""


class DuplicateBudgetError(Exception):
    """Raised when the category already has a budget in this scope."""


class BudgetFamilyRequiredError(Exception):
    """Raised when creating a family budget without belonging to a family."""


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


def _budget_scope(budget: Budget) -> str:
    return "personal" if budget.owner_user_id is not None else "family"


class BudgetService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = BudgetRepository(session)
        self._categories = CategoryRepository(session)
        self._wallets = WalletRepository(session)

    def _spent_base_by_category(
        self, wallet_ids: list[int], start: date, end: date
    ) -> dict[int, int]:
        """Current-month spend per category, converted to the base currency (a
        budget's amount is in the base currency, so spend must be too)."""
        converter = CurrencyConverter(self._session)
        totals: dict[int, int] = {}
        for category_id, currency, total in self._repo.spent_by_category(
            wallet_ids, start, end
        ):
            totals[category_id] = totals.get(category_id, 0) + converter.to_base(
                total, currency
            )
        return totals

    def list_with_spent(
        self, family_id: int | None, user_id: int, scope: str
    ) -> list[tuple[Budget, int]]:
        budgets = self._repo.list(family_id, user_id, scope)
        wallet_ids = self._wallets.visible_wallet_ids(family_id, user_id, scope)
        start, end = _current_month_range()
        spent = self._spent_base_by_category(wallet_ids, start, end)
        return [(b, spent.get(b.category_id, 0)) for b in budgets]

    def create(
        self,
        family_id: int | None,
        user_id: int,
        scope: str,
        category_rid: str,
        amount: int,
    ) -> tuple[Budget, int]:
        category = self._categories.get_visible_by_rid(
            family_id, user_id, category_rid
        )
        if category is None:
            raise CategoryNotFoundError(category_rid)
        if scope == "family":
            if family_id is None:
                raise BudgetFamilyRequiredError()
            owner_user_id: int | None = None
            budget_family_id: int | None = family_id
        else:
            scope = "personal"
            owner_user_id = user_id
            budget_family_id = None
        if (
            self._repo.get_by_category(family_id, user_id, scope, category.id)
            is not None
        ):
            raise DuplicateBudgetError(category_rid)
        budget = self._repo.add(
            budget_family_id, owner_user_id, category.id, amount, user_id
        )
        self._session.commit()
        self._session.refresh(budget)
        return budget, self._month_spent(family_id, user_id, budget)

    def update(
        self, family_id: int | None, user_id: int, rid: str, amount: int
    ) -> tuple[Budget, int]:
        budget = self._repo.get_visible_by_rid(family_id, user_id, rid)
        if budget is None:
            raise BudgetNotFoundError(rid)
        budget.amount = amount
        self._session.commit()
        self._session.refresh(budget)
        return budget, self._month_spent(family_id, user_id, budget)

    def delete(self, family_id: int | None, user_id: int, rid: str) -> None:
        budget = self._repo.get_visible_by_rid(family_id, user_id, rid)
        if budget is None:
            raise BudgetNotFoundError(rid)
        self._repo.delete(budget)
        self._session.commit()

    def _month_spent(
        self, family_id: int | None, user_id: int, budget: Budget
    ) -> int:
        wallet_ids = self._wallets.visible_wallet_ids(
            family_id, user_id, _budget_scope(budget)
        )
        start, end = _current_month_range()
        return self._spent_base_by_category(wallet_ids, start, end).get(
            budget.category_id, 0
        )
