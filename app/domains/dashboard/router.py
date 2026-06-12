"""Dashboard routes — the family's total overview."""

from fastapi import APIRouter

from app.core.deps import CurrentFamily, SessionDep
from app.domains.dashboard.schemas import DashboardSummary
from app.domains.dashboard.service import DashboardService
from app.domains.wallets.schemas import WalletRead

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(session: SessionDep, family_id: CurrentFamily) -> DashboardSummary:
    total_income, total_expense, wallets = DashboardService(session).summary(family_id)
    return DashboardSummary(
        total_income=total_income,
        total_expense=total_expense,
        net_balance=total_income - total_expense,
        wallet_count=len(wallets),
        wallets=[
            WalletRead(
                rid=wallet.rid,
                name=wallet.name,
                balance=balance,
                created_at=wallet.created_at,
            )
            for wallet, balance in wallets
        ],
    )
