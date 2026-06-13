"""Transaction business logic — stateless; session + family_id passed in per call."""

from datetime import date

from sqlalchemy.orm import Session

from app.domains.categories.repository import CategoryRepository
from app.domains.categories.service import CategoryNotFoundError
from app.domains.transactions.models import Transaction, TransactionType
from app.domains.transactions.repository import TransactionRepository
from app.domains.wallets.repository import WalletRepository
from app.domains.wallets.service import WalletNotFoundError


class TransactionService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = TransactionRepository(session)
        self._wallets = WalletRepository(session)
        self._categories = CategoryRepository(session)

    def create(
        self,
        family_id: int,
        user_id: int,
        wallet_rid: str,
        type_: TransactionType,
        amount: int,
        note: str | None,
        occurred_on: date | None,
        category_rid: str | None = None,
    ) -> Transaction:
        # The wallet must belong to this family — this is the tenant guard.
        wallet = self._wallets.get_by_rid(family_id, wallet_rid)
        if wallet is None:
            raise WalletNotFoundError(wallet_rid)
        category_id: int | None = None
        if category_rid is not None:
            category = self._categories.get_by_rid(family_id, category_rid)
            if category is None:
                raise CategoryNotFoundError(category_rid)
            category_id = category.id
        transaction = self._repo.add(
            family_id=family_id,
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

    def list(
        self, family_id: int, wallet_rid: str | None = None, limit: int = 100
    ) -> list[Transaction]:
        wallet_id: int | None = None
        if wallet_rid is not None:
            wallet = self._wallets.get_by_rid(family_id, wallet_rid)
            if wallet is None:
                raise WalletNotFoundError(wallet_rid)
            wallet_id = wallet.id
        return self._repo.list(family_id, wallet_id, limit)
