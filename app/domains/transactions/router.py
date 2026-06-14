"""Transaction routes — thin: delegate to service, map to DTOs."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.deps import CurrentFamily, CurrentUser, SessionDep
from app.domains.categories.schemas import CategoryRead
from app.domains.categories.service import CategoryNotFoundError
from app.domains.transactions.models import Transaction, TransactionType
from app.domains.transactions.schemas import (
    TransactionCreate,
    TransactionCreator,
    TransactionRead,
    TransactionUpdate,
)
from app.domains.transactions.service import (
    NotTransactionOwnerError,
    TransactionNotFoundError,
    TransactionService,
)
from app.domains.wallets.models import WalletScope
from app.domains.wallets.service import WalletNotFoundError

router = APIRouter(prefix="/transactions", tags=["transactions"])

_TXN_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found"
)
_WALLET_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
)
_CATEGORY_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
)
_NOT_OWNER = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="You can only edit or delete transactions you created",
)


def _to_read(transaction: Transaction, current_user_id: int) -> TransactionRead:
    return TransactionRead(
        rid=transaction.rid,
        wallet_rid=transaction.wallet.rid,
        type=transaction.type,  # type: ignore[arg-type]
        amount=transaction.amount,
        note=transaction.note,
        occurred_on=transaction.occurred_on,
        category=(
            CategoryRead.model_validate(transaction.category)
            if transaction.category is not None
            else None
        ),
        created_by=TransactionCreator(
            rid=transaction.creator.rid,
            display_name=transaction.creator.display_name,
        ),
        can_edit=transaction.created_by_user_id == current_user_id,
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
            category_rid=payload.category_rid,
        )
    except WalletNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
        ) from None
    except CategoryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        ) from None
    return _to_read(transaction, current_user.id)


@router.get("", response_model=list[TransactionRead])
def list_transactions(
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
    wallet_rid: str | None = Query(default=None),
    scope: WalletScope = WalletScope.ALL,
    limit: int = Query(default=100, ge=1, le=500),
    type: TransactionType | None = None,
    category_rid: str | None = Query(default=None),
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[TransactionRead]:
    try:
        transactions = TransactionService(session).list(
            family_id,
            current_user.id,
            wallet_rid,
            scope.value,
            limit,
            type_=type,
            category_rid=category_rid,
            date_from=date_from,
            date_to=date_to,
        )
    except WalletNotFoundError:
        raise _WALLET_NOT_FOUND from None
    except CategoryNotFoundError:
        raise _CATEGORY_NOT_FOUND from None
    return [_to_read(transaction, current_user.id) for transaction in transactions]


@router.patch("/{rid}", response_model=TransactionRead)
def update_transaction(
    rid: str,
    payload: TransactionUpdate,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> TransactionRead:
    try:
        transaction = TransactionService(session).update(
            family_id=family_id,
            user_id=current_user.id,
            rid=rid,
            wallet_rid=payload.wallet_rid,
            type_=payload.type,
            amount=payload.amount,
            note=payload.note,
            occurred_on=payload.occurred_on,
            category_rid=payload.category_rid,
        )
    except TransactionNotFoundError:
        raise _TXN_NOT_FOUND from None
    except NotTransactionOwnerError:
        raise _NOT_OWNER from None
    except WalletNotFoundError:
        raise _WALLET_NOT_FOUND from None
    except CategoryNotFoundError:
        raise _CATEGORY_NOT_FOUND from None
    return _to_read(transaction, current_user.id)


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    rid: str,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> Response:
    try:
        TransactionService(session).delete(family_id, current_user.id, rid)
    except TransactionNotFoundError:
        raise _TXN_NOT_FOUND from None
    except NotTransactionOwnerError:
        raise _NOT_OWNER from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
