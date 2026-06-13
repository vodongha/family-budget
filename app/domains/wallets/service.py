"""Wallet business logic — stateless; session + family_id passed in per call."""

from sqlalchemy.orm import Session

from app.domains.wallets.models import Wallet
from app.domains.wallets.repository import WalletRepository


class WalletNotFoundError(Exception):
    """Raised when a wallet rid does not belong to the current family."""


class WalletService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = WalletRepository(session)

    def create(self, family_id: int, name: str) -> tuple[Wallet, int, int]:
        wallet = self._repo.add(family_id, name)
        self._session.commit()
        return wallet, 0, 0

    def list_with_balances(self, family_id: int) -> list[tuple[Wallet, int, int]]:
        wallets = self._repo.list(family_id)
        balances = self._repo.balances_by_wallet(family_id)
        counts = self._repo.counts_by_wallet(family_id)
        return [
            (wallet, balances.get(wallet.id, 0), counts.get(wallet.id, 0))
            for wallet in wallets
        ]

    def get_with_balance(self, family_id: int, rid: str) -> tuple[Wallet, int, int]:
        wallet = self._repo.get_by_rid(family_id, rid)
        if wallet is None:
            raise WalletNotFoundError(rid)
        count = self._repo.counts_by_wallet(family_id).get(wallet.id, 0)
        return wallet, self._repo.balance(family_id, wallet.id), count

    def delete(self, family_id: int, rid: str) -> int:
        """Delete a wallet and all its transactions. Returns the number of
        transactions removed. Raises [WalletNotFoundError] if it's not in the family."""
        wallet = self._repo.get_by_rid(family_id, rid)
        if wallet is None:
            raise WalletNotFoundError(rid)
        deleted = self._repo.delete_with_transactions(family_id, wallet.id)
        self._session.commit()
        return deleted
