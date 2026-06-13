"""Statistics business logic — stateless, family-scoped."""

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.domains.stats.repository import StatsRepository

MAX_MONTHS = 24


class MonthlyPoint:
    def __init__(self, month: str, income: int, expense: int) -> None:
        self.month = month
        self.income = income
        self.expense = expense


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

    def monthly(self, family_id: int, months: int) -> list[MonthlyPoint]:
        months = max(1, min(months, MAX_MONTHS))
        today = datetime.now(UTC).date()
        window = _month_window(today, months)
        start = date(window[0][0], window[0][1], 1)

        income: dict[tuple[int, int], int] = {k: 0 for k in window}
        expense: dict[tuple[int, int], int] = {k: 0 for k in window}
        for occurred_on, type_, amount in self._repo.rows_since(family_id, start):
            key = (occurred_on.year, occurred_on.month)
            if key not in income:
                continue
            if type_ == "income":
                income[key] += amount
            else:
                expense[key] += amount

        return [
            MonthlyPoint(f"{y:04d}-{m:02d}", income[(y, m)], expense[(y, m)])
            for (y, m) in window
        ]
