"""Transfer routes — move money between the family's own wallets."""

from fastapi import APIRouter, HTTPException, Response, status

from app.core.deps import CurrentFamily, CurrentUser, SessionDep
from app.domains.transfers.schemas import TransferCreate, TransferRead
from app.domains.transfers.service import (
    SameWalletError,
    TransferNotFoundError,
    TransferService,
)
from app.domains.wallets.service import WalletNotFoundError

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.post("", response_model=TransferRead, status_code=status.HTTP_201_CREATED)
def create_transfer(
    payload: TransferCreate,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> TransferRead:
    try:
        group_rid, from_rid, to_rid, amount, on = TransferService(session).create(
            family_id=family_id,
            user_id=current_user.id,
            from_wallet_rid=payload.from_wallet_rid,
            to_wallet_rid=payload.to_wallet_rid,
            amount=payload.amount,
            note=payload.note,
            occurred_on=payload.occurred_on,
        )
    except SameWalletError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and destination must be different wallets",
        ) from None
    except WalletNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
        ) from None
    return TransferRead(
        group_rid=group_rid,
        from_wallet_rid=from_rid,
        to_wallet_rid=to_rid,
        amount=amount,
        occurred_on=on,
    )


@router.delete("/{group_rid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transfer(
    group_rid: str,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> Response:
    try:
        TransferService(session).delete(family_id, current_user.id, group_rid)
    except TransferNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transfer not found"
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
