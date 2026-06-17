"""Wallet routes — thin: delegate to service, map to DTOs."""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentUser, OptionalFamily, SessionDep
from app.domains.users.models import UserRole
from app.domains.wallets.models import Wallet, WalletScope
from app.domains.wallets.schemas import (
    WalletCreate,
    WalletDeleteResult,
    WalletRead,
    WalletUpdate,
)
from app.domains.wallets.service import (
    UnsupportedCurrencyError,
    WalletFamilyRequiredError,
    WalletNotFoundError,
    WalletPermissionError,
    WalletService,
)

router = APIRouter(prefix="/wallets", tags=["wallets"])


def _to_read(
    wallet: Wallet, balance: int, viewer_id: int, txn_count: int = 0
) -> WalletRead:
    return WalletRead(
        rid=wallet.rid,
        name=wallet.name,
        icon=wallet.icon,
        color=wallet.color,
        visibility=wallet.visibility,  # type: ignore[arg-type]
        currency=wallet.currency,
        balance=balance,
        txn_count=txn_count,
        created_by_me=wallet.created_by_user_id == viewer_id,
        created_at=wallet.created_at,
    )


@router.post(
    "",
    response_model=WalletRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a wallet",
)
def create_wallet(
    payload: WalletCreate,
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
) -> WalletRead:
    """Create a `family` (shared) or `personal` (private to you) wallet. Defaults
    to family. A `personal` wallet works without a family; a `family` wallet
    requires one (`400` otherwise)."""
    try:
        wallet, balance, count = WalletService(session).create(
            family_id,
            current_user.id,
            payload.name,
            payload.visibility.value,
            payload.icon,
            payload.color,
            payload.currency,
        )
    except WalletFamilyRequiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create a family before adding a shared wallet",
        ) from None
    except UnsupportedCurrencyError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported currency",
        ) from None
    return _to_read(wallet, balance, current_user.id, count)


@router.patch("/{rid}", response_model=WalletRead, summary="Edit a wallet")
def update_wallet(
    rid: str,
    payload: WalletUpdate,
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
) -> WalletRead:
    """Rename a wallet or change its icon/colour. A personal wallet can be edited
    by its owner; a shared family wallet by the family owner or its creator
    (`403` otherwise). `404` if it isn't visible to you. Visibility can't be
    changed."""
    is_owner = current_user.role == UserRole.OWNER.value
    try:
        wallet, balance, count = WalletService(session).update(
            family_id,
            current_user.id,
            rid,
            is_owner,
            name=payload.name,
            icon=payload.icon,
            color=payload.color,
        )
    except WalletNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
        ) from None
    except WalletPermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the family owner or the wallet's creator can edit a shared wallet",
        ) from None
    return _to_read(wallet, balance, current_user.id, count)


@router.get("", response_model=list[WalletRead], summary="List wallets")
def list_wallets(
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
    scope: WalletScope = WalletScope.ALL,
) -> list[WalletRead]:
    """Wallets visible to you with derived balances. `scope`: `all` (family +
    your personal), `family`, or `personal`."""
    return [
        _to_read(wallet, balance, current_user.id, count)
        for wallet, balance, count in WalletService(session).list_with_balances(
            family_id, current_user.id, scope.value
        )
    ]


@router.get("/{rid}", response_model=WalletRead, summary="Get one wallet")
def get_wallet(
    rid: str,
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
) -> WalletRead:
    """One wallet by `rid` with its balance. `404` if it isn't visible to you
    (a wallet you can't see is indistinguishable from one that doesn't exist)."""
    try:
        wallet, balance, count = WalletService(session).get_with_balance(
            family_id, current_user.id, rid
        )
    except WalletNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
        ) from None
    return _to_read(wallet, balance, current_user.id, count)


@router.delete(
    "/{rid}",
    response_model=WalletDeleteResult,
    summary="Delete a wallet",
)
def delete_wallet(
    rid: str,
    session: SessionDep,
    family_id: OptionalFamily,
    current_user: CurrentUser,
) -> WalletDeleteResult:
    """Delete a wallet and all of its transactions. A personal wallet can be
    deleted by its owner; a shared family wallet by the family owner or its
    creator (it destroys shared history)."""
    is_owner = current_user.role == UserRole.OWNER.value
    try:
        deleted = WalletService(session).delete(
            family_id, current_user.id, rid, is_owner
        )
    except WalletNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
        ) from None
    except WalletPermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the family owner or the wallet's creator can delete a shared wallet",
        ) from None
    return WalletDeleteResult(deleted_transactions=deleted)
