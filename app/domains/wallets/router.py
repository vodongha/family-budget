"""Wallet routes — thin: delegate to service, map to DTOs."""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentFamily, SessionDep
from app.domains.wallets.models import Wallet
from app.domains.wallets.schemas import WalletCreate, WalletRead
from app.domains.wallets.service import WalletNotFoundError, WalletService

router = APIRouter(prefix="/wallets", tags=["wallets"])


def _to_read(wallet: Wallet, balance: int) -> WalletRead:
    return WalletRead(
        rid=wallet.rid, name=wallet.name, balance=balance, created_at=wallet.created_at
    )


@router.post("", response_model=WalletRead, status_code=status.HTTP_201_CREATED)
def create_wallet(
    payload: WalletCreate, session: SessionDep, family_id: CurrentFamily
) -> WalletRead:
    wallet, balance = WalletService(session).create(family_id, payload.name)
    return _to_read(wallet, balance)


@router.get("", response_model=list[WalletRead])
def list_wallets(session: SessionDep, family_id: CurrentFamily) -> list[WalletRead]:
    return [
        _to_read(wallet, balance)
        for wallet, balance in WalletService(session).list_with_balances(family_id)
    ]


@router.get("/{rid}", response_model=WalletRead)
def get_wallet(rid: str, session: SessionDep, family_id: CurrentFamily) -> WalletRead:
    try:
        wallet, balance = WalletService(session).get_with_balance(family_id, rid)
    except WalletNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
        ) from None
    return _to_read(wallet, balance)
