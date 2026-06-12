"""Dashboard business logic — composes wallet balances and family totals."""

from sqlalchemy.orm import Session

from app.domains.transactions.repository import TransactionRepository
from app.domains.wallets.models import Wallet
from app.domains.wallets.service import WalletService


class DashboardService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._wallets = WalletService(session)
        self._transactions = TransactionRepository(session)

    def summary(self, family_id: int) -> tuple[int, int, list[tuple[Wallet, int]]]:
        """Return (total_income, total_expense, [(wallet, balance), ...])."""
        total_income, total_expense = self._transactions.family_totals(family_id)
        wallets = self._wallets.list_with_balances(family_id)
        return total_income, total_expense, wallets
