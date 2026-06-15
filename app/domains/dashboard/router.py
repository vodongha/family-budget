"""Dashboard routes — the family's total overview."""

from fastapi import APIRouter

from app.core.deps import CurrentUser, OptionalFamily, SessionDep
from app.domains.dashboard.schemas import DashboardSummary
from app.domains.dashboard.service import DashboardService
from app.domains.wallets.models import WalletScope
from app.domains.wallets.schemas import WalletRead

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Family overview",
)
def summary(
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
    scope: WalletScope = WalletScope.ALL,
) -> DashboardSummary:
    """Net balance, total income/expense and per-wallet balances for the chosen
    `scope` (`all` / `family` / `personal`). Transfers are excluded from totals."""
    total_income, total_expense, wallets = DashboardService(session).summary(
        family_id, current_user.id, scope.value
    )
    return DashboardSummary(
        total_income=total_income,
        total_expense=total_expense,
        net_balance=total_income - total_expense,
        wallet_count=len(wallets),
        wallets=[
            WalletRead(
                rid=wallet.rid,
                name=wallet.name,
                icon=wallet.icon,
                color=wallet.color,
                visibility=wallet.visibility,  # type: ignore[arg-type]
                balance=balance,
                txn_count=count,
                created_by_me=wallet.created_by_user_id == current_user.id,
                created_at=wallet.created_at,
            )
            for wallet, balance, count in wallets
        ],
    )
