"""Dashboard business logic — composes wallet balances and family totals.

Per-wallet balances stay in each wallet's own currency (for display); the family
totals (income/expense/net) convert every wallet's figures to the base currency
so a household with mixed-currency wallets gets one meaningful number."""

from sqlalchemy.orm import Session

from app.domains.rates.service import CurrencyConverter
from app.domains.transactions.repository import TransactionRepository
from app.domains.wallets.models import Wallet, WalletScope
from app.domains.wallets.service import WalletService


class DashboardService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._wallets = WalletService(session)
        self._transactions = TransactionRepository(session)

    def summary(
        self, family_id: int | None, user_id: int, scope: str = WalletScope.ALL.value
    ) -> tuple[int, int, list[tuple[Wallet, int, int]]]:
        """Return (total_income, total_expense, [(wallet, balance, txn_count), ...])
        over the wallets the caller may see under ``scope``. Per-wallet balances
        are in the wallet's own currency; the totals are in the base currency.
        Works without a family (personal scope)."""
        wallets = self._wallets.list_with_balances(family_id, user_id, scope)
        by_wallet = self._transactions.totals_by_wallet(
            [wallet.id for wallet, _, _ in wallets]
        )
        converter = CurrencyConverter(self._session)
        total_income = 0
        total_expense = 0
        for wallet, _balance, _count in wallets:
            income, expense = by_wallet.get(wallet.id, (0, 0))
            total_income += converter.to_base(income, wallet.currency)
            total_expense += converter.to_base(expense, wallet.currency)
        return total_income, total_expense, wallets
