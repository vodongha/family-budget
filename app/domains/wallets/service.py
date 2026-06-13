"""Wallet business logic — stateless; session + family_id passed in per call."""

from sqlalchemy.orm import Session

from app.domains.wallets.models import Wallet, WalletScope, WalletVisibility
from app.domains.wallets.repository import WalletRepository


class WalletNotFoundError(Exception):
    """Raised when a wallet rid is not visible to the caller in this family."""


class WalletPermissionError(Exception):
    """Raised when the caller may see a wallet but isn't allowed to delete it."""


class WalletService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = WalletRepository(session)

    def create(
        self,
        family_id: int,
        user_id: int,
        name: str,
        visibility: str = WalletVisibility.FAMILY.value,
    ) -> tuple[Wallet, int, int]:
        # A personal wallet is owned by (and private to) its creator.
        owner_user_id = (
            user_id if visibility == WalletVisibility.PERSONAL.value else None
        )
        wallet = self._repo.add(family_id, name, visibility, owner_user_id)
        self._session.commit()
        return wallet, 0, 0

    def list_with_balances(
        self, family_id: int, user_id: int, scope: str = WalletScope.ALL.value
    ) -> list[tuple[Wallet, int, int]]:
        wallets = self._repo.list(family_id, user_id, scope)
        ids = [wallet.id for wallet in wallets]
        balances = self._repo.balances_by_wallet(family_id, ids)
        counts = self._repo.counts_by_wallet(family_id, ids)
        return [
            (wallet, balances.get(wallet.id, 0), counts.get(wallet.id, 0))
            for wallet in wallets
        ]

    def get_with_balance(
        self, family_id: int, user_id: int, rid: str
    ) -> tuple[Wallet, int, int]:
        wallet = self._repo.get_visible_by_rid(family_id, user_id, rid)
        if wallet is None:
            raise WalletNotFoundError(rid)
        count = self._repo.counts_by_wallet(family_id, [wallet.id]).get(wallet.id, 0)
        return wallet, self._repo.balance(family_id, wallet.id), count

    def delete(
        self, family_id: int, user_id: int, rid: str, requester_is_owner: bool
    ) -> int:
        """Delete a wallet and all its transactions. Returns the number of
        transactions removed.

        - A **personal** wallet may be deleted by its owner (guaranteed by
          visibility — only the owner can see it).
        - A **family** wallet may be deleted only by the family owner, because it
          destroys shared history.

        Raises [WalletNotFoundError] if not visible, [WalletPermissionError] if
        visible but not deletable by this caller."""
        wallet = self._repo.get_visible_by_rid(family_id, user_id, rid)
        if wallet is None:
            raise WalletNotFoundError(rid)
        if (
            wallet.visibility == WalletVisibility.FAMILY.value
            and not requester_is_owner
        ):
            raise WalletPermissionError(rid)
        deleted = self._repo.delete_with_transactions(family_id, wallet.id)
        self._session.commit()
        return deleted
