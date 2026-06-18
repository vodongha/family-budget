"""Pydantic DTOs for the family dashboard."""

from pydantic import BaseModel

from app.domains.wallets.schemas import WalletRead


class DashboardSummary(BaseModel):
    # Totals are integer minor units of `currency` (the display currency);
    # per-wallet balances stay in each wallet's own currency.
    total_income: int
    total_expense: int
    net_balance: int  # total_income - total_expense (== sum of wallet balances)
    currency: str  # the currency the totals above are expressed in
    wallet_count: int
    wallets: list[WalletRead]
