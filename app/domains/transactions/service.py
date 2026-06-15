"""Transaction business logic — stateless; session + family_id passed in per call."""

from datetime import date

from sqlalchemy.orm import Session

from app.domains.categories.repository import CategoryRepository
from app.domains.categories.service import CategoryNotFoundError
from app.domains.transactions.models import Transaction, TransactionType
from app.domains.transactions.repository import TransactionRepository
from app.domains.wallets.models import WalletScope
from app.domains.wallets.repository import WalletRepository
from app.domains.wallets.service import WalletNotFoundError


class TransactionNotFoundError(Exception):
    """Raised when a transaction rid is unknown or not visible to the caller."""


class NotTransactionOwnerError(Exception):
    """Raised when someone tries to edit/delete a transaction they didn't create."""


class TransactionService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = TransactionRepository(session)
        self._wallets = WalletRepository(session)
        self._categories = CategoryRepository(session)

    def create(
        self,
        family_id: int | None,
        user_id: int,
        wallet_rid: str,
        type_: TransactionType,
        amount: int,
        note: str | None,
        occurred_on: date | None,
        category_rid: str | None = None,
    ) -> Transaction:
        # The wallet must be visible to this caller — tenant + privacy guard.
        # (A member can't write into another member's personal wallet.)
        wallet = self._wallets.get_visible_by_rid(family_id, user_id, wallet_rid)
        if wallet is None:
            raise WalletNotFoundError(wallet_rid)
        category_id = self._resolve_category_id(family_id, user_id, category_rid)
        transaction = self._repo.add(
            # Mirror the wallet's family (null for a personal wallet).
            family_id=wallet.family_id,
            wallet_id=wallet.id,
            created_by_user_id=user_id,
            type_=type_,
            amount=amount,
            note=note,
            occurred_on=occurred_on or date.today(),
            category_id=category_id,
        )
        self._session.commit()
        return transaction

    def _resolve_category_id(
        self, family_id: int | None, user_id: int, category_rid: str | None
    ) -> int | None:
        if category_rid is None:
            return None
        # The category must be visible to the caller (their personal one or one
        # of their family's).
        category = self._categories.get_visible_by_rid(
            family_id, user_id, category_rid
        )
        if category is None:
            raise CategoryNotFoundError(category_rid)
        return category.id

    def list(
        self,
        family_id: int | None,
        user_id: int,
        wallet_rid: str | None = None,
        scope: str = WalletScope.ALL.value,
        limit: int = 100,
        type_: TransactionType | None = None,
        category_rid: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Transaction]:
        category_id = self._resolve_category_id(family_id, user_id, category_rid)
        type_value = type_.value if type_ is not None else None
        filters = {
            "limit": limit,
            "type_": type_value,
            "category_id": category_id,
            "date_from": date_from,
            "date_to": date_to,
        }
        # A specific wallet: it must be visible to the caller.
        if wallet_rid is not None:
            wallet = self._wallets.get_visible_by_rid(family_id, user_id, wallet_rid)
            if wallet is None:
                raise WalletNotFoundError(wallet_rid)
            return self._repo.list(wallet_id=wallet.id, **filters)
        # Otherwise: only transactions in wallets the caller may see (per scope).
        ids = self._wallets.visible_wallet_ids(family_id, user_id, scope)
        return self._repo.list(wallet_ids=ids, **filters)

    def update(
        self,
        family_id: int | None,
        user_id: int,
        rid: str,
        wallet_rid: str,
        type_: TransactionType,
        amount: int,
        note: str | None,
        occurred_on: date | None,
        category_rid: str | None = None,
    ) -> Transaction:
        transaction = self._repo.get_by_rid(rid)
        # Must exist and live in a wallet the caller may see (privacy guard).
        if transaction is None or (
            self._wallets.get_visible_by_rid(
                family_id, user_id, transaction.wallet.rid
            )
            is None
        ):
            raise TransactionNotFoundError(rid)
        if transaction.created_by_user_id != user_id:
            raise NotTransactionOwnerError(rid)
        wallet = self._wallets.get_visible_by_rid(family_id, user_id, wallet_rid)
        if wallet is None:
            raise WalletNotFoundError(wallet_rid)
        transaction.wallet_id = wallet.id
        transaction.type = type_.value
        transaction.amount = amount
        transaction.note = note
        transaction.occurred_on = occurred_on or date.today()
        transaction.category_id = self._resolve_category_id(
            family_id, user_id, category_rid
        )
        self._session.commit()
        self._session.refresh(transaction)
        return transaction

    def delete(self, family_id: int | None, user_id: int, rid: str) -> None:
        transaction = self._repo.get_by_rid(rid)
        if transaction is None or (
            self._wallets.get_visible_by_rid(
                family_id, user_id, transaction.wallet.rid
            )
            is None
        ):
            raise TransactionNotFoundError(rid)
        if transaction.created_by_user_id != user_id:
            raise NotTransactionOwnerError(rid)
        self._repo.delete(transaction)
        self._session.commit()
