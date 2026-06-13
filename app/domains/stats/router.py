"""Statistics routes — family-scoped, read-only."""

from fastapi import APIRouter

from app.core.deps import CurrentFamily, SessionDep
from app.domains.stats.schemas import MonthlyPoint
from app.domains.stats.service import StatsService

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/monthly", response_model=list[MonthlyPoint])
def monthly(
    session: SessionDep, family_id: CurrentFamily, months: int = 6
) -> list[MonthlyPoint]:
    points = StatsService(session).monthly(family_id, months)
    return [
        MonthlyPoint(month=p.month, income=p.income, expense=p.expense)
        for p in points
    ]
