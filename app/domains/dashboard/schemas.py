"""Pydantic DTOs for the family dashboard."""

from pydantic import BaseModel

from app.domains.wallets.schemas import WalletRead


class DashboardSummary(BaseModel):
    # All amounts are integer minor units (đồng).
    total_income: int
    total_expense: int
    net_balance: int  # total_income - total_expense (== sum of wallet balances)
    wallet_count: int
    wallets: list[WalletRead]
