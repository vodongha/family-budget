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

    def create(self, family_id: int, name: str) -> tuple[Wallet, int]:
        wallet = self._repo.add(family_id, name)
        self._session.commit()
        return wallet, 0

    def list_with_balances(self, family_id: int) -> list[tuple[Wallet, int]]:
        wallets = self._repo.list(family_id)
        balances = self._repo.balances_by_wallet(family_id)
        return [(wallet, balances.get(wallet.id, 0)) for wallet in wallets]

    def get_with_balance(self, family_id: int, rid: str) -> tuple[Wallet, int]:
        wallet = self._repo.get_by_rid(family_id, rid)
        if wallet is None:
            raise WalletNotFoundError(rid)
        return wallet, self._repo.balance(family_id, wallet.id)
