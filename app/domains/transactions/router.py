"""Transaction routes — thin: delegate to service, map to DTOs."""

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import CurrentFamily, CurrentUser, SessionDep
from app.domains.transactions.models import Transaction
from app.domains.transactions.schemas import TransactionCreate, TransactionRead
from app.domains.transactions.service import TransactionService
from app.domains.wallets.service import WalletNotFoundError

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _to_read(transaction: Transaction) -> TransactionRead:
    return TransactionRead(
        rid=transaction.rid,
        wallet_rid=transaction.wallet.rid,
        type=transaction.type,  # type: ignore[arg-type]
        amount=transaction.amount,
        note=transaction.note,
        occurred_on=transaction.occurred_on,
        created_at=transaction.created_at,
    )


@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> TransactionRead:
    try:
        transaction = TransactionService(session).create(
            family_id=family_id,
            user_id=current_user.id,
            wallet_rid=payload.wallet_rid,
            type_=payload.type,
            amount=payload.amount,
            note=payload.note,
            occurred_on=payload.occurred_on,
        )
    except WalletNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
        ) from None
    return _to_read(transaction)


@router.get("", response_model=list[TransactionRead])
def list_transactions(
    session: SessionDep,
    family_id: CurrentFamily,
    wallet_rid: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[TransactionRead]:
    try:
        transactions = TransactionService(session).list(family_id, wallet_rid, limit)
    except WalletNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
        ) from None
    return [_to_read(transaction) for transaction in transactions]
