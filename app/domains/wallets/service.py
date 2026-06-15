"""Wallet business logic — stateless. ``family_id`` may be ``None`` (the caller
has no family): personal wallets work without one; family wallets require it."""

from sqlalchemy.orm import Session

from app.domains.wallets.models import Wallet, WalletScope, WalletVisibility
from app.domains.wallets.repository import WalletRepository


class WalletNotFoundError(Exception):
    """Raised when a wallet rid is not visible to the caller."""


class WalletPermissionError(Exception):
    """Raised when the caller may see a wallet but isn't allowed to edit/delete it."""


class WalletFamilyRequiredError(Exception):
    """Raised when creating a shared (family) wallet without belonging to a family."""


class WalletService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = WalletRepository(session)

    def create(
        self,
        family_id: int | None,
        user_id: int,
        name: str,
        visibility: str = WalletVisibility.FAMILY.value,
        icon: str | None = None,
        color: str | None = None,
    ) -> tuple[Wallet, int, int]:
        if visibility == WalletVisibility.PERSONAL.value:
            # Personal wallets belong to the user, independent of any family.
            owner_user_id: int | None = user_id
            wallet_family_id: int | None = None
        else:
            # A shared wallet needs a family to share within.
            if family_id is None:
                raise WalletFamilyRequiredError()
            owner_user_id = None
            wallet_family_id = family_id
        wallet = self._repo.add(
            wallet_family_id,
            name,
            visibility,
            owner_user_id,
            icon,
            color,
            created_by_user_id=user_id,
        )
        self._session.commit()
        return wallet, 0, 0

    @staticmethod
    def _can_manage(wallet: Wallet, user_id: int, requester_is_owner: bool) -> bool:
        """Whether ``user_id`` may edit/delete ``wallet``.

        A **personal** wallet is private to its owner (only they can see it), so
        seeing it means they may manage it. A **shared** family wallet may be
        managed by the family owner **or** the member who created it."""
        if wallet.visibility != WalletVisibility.FAMILY.value:
            return True
        return requester_is_owner or wallet.created_by_user_id == user_id

    def update(
        self,
        family_id: int | None,
        user_id: int,
        rid: str,
        requester_is_owner: bool,
        *,
        name: str | None = None,
        icon: str | None = None,
        color: str | None = None,
    ) -> tuple[Wallet, int, int]:
        """Edit a wallet's name/icon/colour. Permission mirrors delete: a personal
        wallet by its owner (guaranteed by visibility), a shared family wallet by
        the family owner or its creator. Only provided (non-None) fields change.

        Raises [WalletNotFoundError] if not visible, [WalletPermissionError] if
        visible but not editable by this caller."""
        wallet = self._repo.get_visible_by_rid(family_id, user_id, rid)
        if wallet is None:
            raise WalletNotFoundError(rid)
        if not self._can_manage(wallet, user_id, requester_is_owner):
            raise WalletPermissionError(rid)
        if name is not None:
            wallet.name = name
        if icon is not None:
            wallet.icon = icon
        if color is not None:
            wallet.color = color
        self._session.commit()
        count = self._repo.counts_by_wallet([wallet.id]).get(wallet.id, 0)
        return wallet, self._repo.balance(wallet.id), count

    def list_with_balances(
        self, family_id: int | None, user_id: int, scope: str = WalletScope.ALL.value
    ) -> list[tuple[Wallet, int, int]]:
        wallets = self._repo.list(family_id, user_id, scope)
        ids = [wallet.id for wallet in wallets]
        balances = self._repo.balances_by_wallet(ids)
        counts = self._repo.counts_by_wallet(ids)
        return [
            (wallet, balances.get(wallet.id, 0), counts.get(wallet.id, 0))
            for wallet in wallets
        ]

    def get_with_balance(
        self, family_id: int | None, user_id: int, rid: str
    ) -> tuple[Wallet, int, int]:
        wallet = self._repo.get_visible_by_rid(family_id, user_id, rid)
        if wallet is None:
            raise WalletNotFoundError(rid)
        count = self._repo.counts_by_wallet([wallet.id]).get(wallet.id, 0)
        return wallet, self._repo.balance(wallet.id), count

    def delete(
        self,
        family_id: int | None,
        user_id: int,
        rid: str,
        requester_is_owner: bool,
    ) -> int:
        """Delete a wallet and all its transactions. Returns the number of
        transactions removed.

        - A **personal** wallet may be deleted by its owner (guaranteed by
          visibility — only the owner can see it).
        - A **family** wallet may be deleted by the family owner or the member who
          created it (it destroys shared history).

        Raises [WalletNotFoundError] if not visible, [WalletPermissionError] if
        visible but not deletable by this caller."""
        wallet = self._repo.get_visible_by_rid(family_id, user_id, rid)
        if wallet is None:
            raise WalletNotFoundError(rid)
        if not self._can_manage(wallet, user_id, requester_is_owner):
            raise WalletPermissionError(rid)
        deleted = self._repo.delete_with_transactions(wallet.id)
        self._session.commit()
        return deleted
