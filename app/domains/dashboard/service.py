"""Dashboard business logic — composes wallet balances and family totals."""

from sqlalchemy.orm import Session

from app.domains.transactions.repository import TransactionRepository
from app.domains.wallets.models import Wallet, WalletScope
from app.domains.wallets.service import WalletService


class DashboardService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._wallets = WalletService(session)
        self._transactions = TransactionRepository(session)

    def summary(
        self, family_id: int, user_id: int, scope: str = WalletScope.ALL.value
    ) -> tuple[int, int, list[tuple[Wallet, int, int]]]:
        """Return (total_income, total_expense, [(wallet, balance, txn_count), ...])
        over the wallets the caller may see under ``scope``."""
        wallets = self._wallets.list_with_balances(family_id, user_id, scope)
        ids = [wallet.id for wallet, _, _ in wallets]
        total_income, total_expense = self._transactions.family_totals(family_id, ids)
        return total_income, total_expense, wallets
