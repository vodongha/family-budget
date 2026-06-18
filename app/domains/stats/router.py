"""Statistics routes — family-scoped, read-only."""

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DisplayCurrency, OptionalFamily, SessionDep
from app.domains.categories.models import CategoryKind
from app.domains.stats.schemas import CalendarDay, CategorySlice, MonthlyPoint
from app.domains.stats.service import StatsService
from app.domains.wallets.models import WalletScope

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get(
    "/monthly",
    response_model=list[MonthlyPoint],
    summary="Monthly income/expense series",
)
def monthly(
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
    display_currency: DisplayCurrency,
    months: int = 6,
    scope: WalletScope = WalletScope.ALL,
) -> list[MonthlyPoint]:
    """Income and expense totals per month for the last `months` months, scoped by
    `scope`. Transfers are excluded. Amounts are in `display_currency`."""
    points = StatsService(session).monthly(
        family_id, current_user.id, months, scope.value, display_currency
    )
    return [
        MonthlyPoint(month=p.month, income=p.income, expense=p.expense)
        for p in points
    ]


@router.get(
    "/calendar",
    response_model=list[CalendarDay],
    summary="Per-day totals for a month",
)
def calendar(
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
    display_currency: DisplayCurrency,
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    scope: WalletScope = WalletScope.ALL,
) -> list[CalendarDay]:
    """Income/expense per day for the given month, in `display_currency`. Only days
    with activity are returned; boundary-crossing transfers count, internal ones
    don't."""
    points = StatsService(session).calendar(
        family_id, current_user.id, year, month, scope.value, display_currency
    )
    return [
        CalendarDay(day=p.day, income=p.income, expense=p.expense) for p in points
    ]


@router.get(
    "/by-category",
    response_model=list[CategorySlice],
    summary="Per-category breakdown",
)
def by_category(
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
    display_currency: DisplayCurrency,
    kind: CategoryKind = CategoryKind.EXPENSE,
    months: int = 6,
    scope: WalletScope = WalletScope.ALL,
) -> list[CategorySlice]:
    """Totals per category for one `kind` (`expense`/`income`) over `months`,
    sorted by amount descending. Uncategorized entries fold into one bucket.
    Amounts are in `display_currency`."""
    slices = StatsService(session).by_category(
        family_id, current_user.id, kind.value, months, scope.value, display_currency
    )
    return [
        CategorySlice(
            category_rid=s.category_rid,
            name=s.name,
            icon=s.icon,
            color=s.color,
            default_key=s.default_key,
            amount=s.amount,
        )
        for s in slices
    ]
