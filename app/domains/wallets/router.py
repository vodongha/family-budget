"""Wallet routes — thin: delegate to service, map to DTOs."""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentFamily, CurrentUser, SessionDep
from app.domains.users.models import UserRole
from app.domains.wallets.models import Wallet
from app.domains.wallets.schemas import WalletCreate, WalletDeleteResult, WalletRead
from app.domains.wallets.service import WalletNotFoundError, WalletService

router = APIRouter(prefix="/wallets", tags=["wallets"])


def _to_read(wallet: Wallet, balance: int, txn_count: int = 0) -> WalletRead:
    return WalletRead(
        rid=wallet.rid,
        name=wallet.name,
        balance=balance,
        txn_count=txn_count,
        created_at=wallet.created_at,
    )


@router.post("", response_model=WalletRead, status_code=status.HTTP_201_CREATED)
def create_wallet(
    payload: WalletCreate, session: SessionDep, family_id: CurrentFamily
) -> WalletRead:
    wallet, balance, count = WalletService(session).create(family_id, payload.name)
    return _to_read(wallet, balance, count)


@router.get("", response_model=list[WalletRead])
def list_wallets(session: SessionDep, family_id: CurrentFamily) -> list[WalletRead]:
    return [
        _to_read(wallet, balance, count)
        for wallet, balance, count in WalletService(session).list_with_balances(family_id)
    ]


@router.get("/{rid}", response_model=WalletRead)
def get_wallet(rid: str, session: SessionDep, family_id: CurrentFamily) -> WalletRead:
    try:
        wallet, balance, count = WalletService(session).get_with_balance(family_id, rid)
    except WalletNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
        ) from None
    return _to_read(wallet, balance, count)


@router.delete("/{rid}", response_model=WalletDeleteResult)
def delete_wallet(
    rid: str,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> WalletDeleteResult:
    """Delete a wallet and all of its transactions. Owner-only — this destroys
    shared family history."""
    if current_user.role != UserRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the family owner can delete a wallet",
        )
    try:
        deleted = WalletService(session).delete(family_id, rid)
    except WalletNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
        ) from None
    return WalletDeleteResult(deleted_transactions=deleted)
