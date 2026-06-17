"""Statistics business logic — stateless, family-scoped."""

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.domains.rates.service import CurrencyConverter
from app.domains.stats.repository import StatsRepository
from app.domains.transactions.models import TransactionType
from app.domains.transactions.repository import TransactionRepository
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
        self._session = session
        self._repo = StatsRepository(session)
        self._wallets = WalletRepository(session)
        self._txns = TransactionRepository(session)

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

        converter = CurrencyConverter(self._session)
        income: dict[tuple[int, int], int] = {k: 0 for k in window}
        expense: dict[tuple[int, int], int] = {k: 0 for k in window}
        for occurred_on, type_, amount, currency in self._repo.rows_since(
            start, wallet_ids
        ):
            key = (occurred_on.year, occurred_on.month)
            if key not in income:
                continue
            # Convert to the base currency so a mixed-currency household has one
            # comparable trend. Only income/expense count; transfer legs move money
            # between the family's own wallets and must not inflate either total.
            base = converter.to_base(amount, currency)
            if type_ == "income":
                income[key] += base
            elif type_ == "expense":
                expense[key] += base

        # Transfers crossing the scope boundary (e.g. personal→family) count as
        # income/expense for this scope; internal transfers are ignored.
        for occurred_on, type_, amount, currency in self._txns.boundary_transfer_legs(
            wallet_ids, start
        ):
            key = (occurred_on.year, occurred_on.month)
            if key not in income:
                continue
            base = converter.to_base(amount, currency)
            if type_ == TransactionType.TRANSFER_IN.value:
                income[key] += base
            else:
                expense[key] += base

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
        # running total (in base currency) plus the category's display metadata.
        converter = CurrencyConverter(self._session)
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
            slice_.amount += converter.to_base(row.amount, row.currency)

        # Boundary-crossing transfers (e.g. personal→family) are income/expense
        # for this scope but have no category, so they fold into the uncategorized
        # bucket of the matching kind.
        for _on, type_, amount, currency in self._txns.boundary_transfer_legs(
            wallet_ids, start
        ):
            leg_kind = (
                "income"
                if type_ == TransactionType.TRANSFER_IN.value
                else "expense"
            )
            if leg_kind != kind:
                continue
            slice_ = buckets.get(None)
            if slice_ is None:
                slice_ = CategorySlice(
                    category_rid=None,
                    name=None,
                    icon=None,
                    color=None,
                    default_key="uncategorized",
                    amount=0,
                )
                buckets[None] = slice_
            slice_.amount += converter.to_base(amount, currency)

        return sorted(buckets.values(), key=lambda s: s.amount, reverse=True)
