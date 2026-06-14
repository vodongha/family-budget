"""Statistics routes — family-scoped, read-only."""

from fastapi import APIRouter

from app.core.deps import CurrentFamily, CurrentUser, SessionDep
from app.domains.categories.models import CategoryKind
from app.domains.stats.schemas import CategorySlice, MonthlyPoint
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
    family_id: CurrentFamily,
    current_user: CurrentUser,
    months: int = 6,
    scope: WalletScope = WalletScope.ALL,
) -> list[MonthlyPoint]:
    """Income and expense totals per month for the last `months` months, scoped by
    `scope`. Transfers are excluded."""
    points = StatsService(session).monthly(
        family_id, current_user.id, months, scope.value
    )
    return [
        MonthlyPoint(month=p.month, income=p.income, expense=p.expense)
        for p in points
    ]


@router.get(
    "/by-category",
    response_model=list[CategorySlice],
    summary="Per-category breakdown",
)
def by_category(
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
    kind: CategoryKind = CategoryKind.EXPENSE,
    months: int = 6,
    scope: WalletScope = WalletScope.ALL,
) -> list[CategorySlice]:
    """Totals per category for one `kind` (`expense`/`income`) over `months`,
    sorted by amount descending. Uncategorized entries fold into one bucket."""
    slices = StatsService(session).by_category(
        family_id, current_user.id, kind.value, months, scope.value
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
