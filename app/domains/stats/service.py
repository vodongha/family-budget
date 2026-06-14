"""Statistics business logic — stateless, family-scoped."""

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.domains.stats.repository import StatsRepository
from app.domains.wallets.models import WalletScope
from app.domains.wallets.repository import WalletRepository

MAX_MONTHS = 24


class MonthlyPoint:
    def __init__(self, month: str, income: int, expense: int) -> None:
        self.month = month
        self.income = income
        self.expense = expense


class CategorySlice:
    """Total spent/earned under one category over the window.

    ``category_rid`` is ``None`` for the uncategorized bucket (``default_key``
    ``"uncategorized"`` so the client can localize it).
    """

    def __init__(
        self,
        category_rid: str | None,
        name: str | None,
        icon: str | None,
        color: str | None,
        default_key: str | None,
        amount: int,
    ) -> None:
        self.category_rid = category_rid
        self.name = name
        self.icon = icon
        self.color = color
        self.default_key = default_key
        self.amount = amount


def _month_window(today: date, months: int) -> list[tuple[int, int]]:
    """The (year, month) tuples for the last ``months`` months, oldest first."""
    base = today.year * 12 + (today.month - 1)
    window: list[tuple[int, int]] = []
    for i in range(months):
        idx = base - (months - 1 - i)
        window.append((idx // 12, idx % 12 + 1))
    return window


class StatsService:
    def __init__(self, session: Session) -> None:
        self._repo = StatsRepository(session)
        self._wallets = WalletRepository(session)

    def monthly(
        self,
        family_id: int | None,
        user_id: int,
        months: int,
        scope: str = WalletScope.ALL.value,
    ) -> list[MonthlyPoint]:
        months = max(1, min(months, MAX_MONTHS))
        today = datetime.now(UTC).date()
        window = _month_window(today, months)
        start = date(window[0][0], window[0][1], 1)
        wallet_ids = self._wallets.visible_wallet_ids(family_id, user_id, scope)

        income: dict[tuple[int, int], int] = {k: 0 for k in window}
        expense: dict[tuple[int, int], int] = {k: 0 for k in window}
        for occurred_on, type_, amount in self._repo.rows_since(start, wallet_ids):
            key = (occurred_on.year, occurred_on.month)
            if key not in income:
                continue
            # Only income/expense count toward the trend; transfer legs move money
            # between the family's own wallets and must not inflate either total.
            if type_ == "income":
                income[key] += amount
            elif type_ == "expense":
                expense[key] += amount

        return [
            MonthlyPoint(f"{y:04d}-{m:02d}", income[(y, m)], expense[(y, m)])
            for (y, m) in window
        ]

    def by_category(
        self,
        family_id: int | None,
        user_id: int,
        kind: str,
        months: int,
        scope: str = WalletScope.ALL.value,
    ) -> list[CategorySlice]:
        """Totals grouped by category for one kind (expense/income), over the
        last ``months`` months, restricted to the wallets the caller may see.
        Uncategorized transactions fold into a single bucket with ``category_rid``
        ``None``. Sorted by amount, descending."""
        months = max(1, min(months, MAX_MONTHS))
        today = datetime.now(UTC).date()
        window = _month_window(today, months)
        start = date(window[0][0], window[0][1], 1)
        wallet_ids = self._wallets.visible_wallet_ids(family_id, user_id, scope)

        # Keyed by category_rid (None for uncategorized). Value carries the
        # running total plus the category's display metadata.
        buckets: dict[str | None, CategorySlice] = {}
        for row in self._repo.category_rows_since(start, wallet_ids):
            if row.type != kind:
                continue
            slice_ = buckets.get(row.category_rid)
            if slice_ is None:
                slice_ = CategorySlice(
                    category_rid=row.category_rid,
                    name=row.name,
                    icon=row.icon,
                    color=row.color,
                    default_key=(
                        row.default_key
                        if row.category_rid is not None
                        else "uncategorized"
                    ),
                    amount=0,
                )
                buckets[row.category_rid] = slice_
            slice_.amount += row.amount

        return sorted(buckets.values(), key=lambda s: s.amount, reverse=True)
