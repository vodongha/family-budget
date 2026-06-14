"""Wallet-to-wallet transfer logic — stateless, family-scoped.

A transfer is two linked transaction legs sharing a ``transfer_group_rid``:
``transfer_out`` from the source wallet and ``transfer_in`` to the destination.
Both wallets must be visible to the caller (tenant + privacy guard). Legs affect
wallet balances but are excluded from income/expense totals and statistics.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.domains.transactions.models import TransactionType
from app.domains.transactions.repository import TransactionRepository
from app.domains.users.models import new_rid
from app.domains.wallets.repository import WalletRepository
from app.domains.wallets.service import WalletNotFoundError


class SameWalletError(Exception):
    """Source and destination wallets are the same."""


class TransferNotFoundError(Exception):
    """No visible transfer with the given group rid."""


class TransferService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._txns = TransactionRepository(session)
        self._wallets = WalletRepository(session)

    def create(
        self,
        family_id: int | None,
        user_id: int,
        from_wallet_rid: str,
        to_wallet_rid: str,
        amount: int,
        note: str | None,
        occurred_on: date | None,
    ) -> tuple[str, str, str, int, date]:
        if from_wallet_rid == to_wallet_rid:
            raise SameWalletError()
        src = self._wallets.get_visible_by_rid(family_id, user_id, from_wallet_rid)
        if src is None:
            raise WalletNotFoundError(from_wallet_rid)
        dst = self._wallets.get_visible_by_rid(family_id, user_id, to_wallet_rid)
        if dst is None:
            raise WalletNotFoundError(to_wallet_rid)

        group_rid = new_rid()
        on = occurred_on or date.today()
        self._txns.add(
            family_id=src.family_id,
            wallet_id=src.id,
            created_by_user_id=user_id,
            type_=TransactionType.TRANSFER_OUT,
            amount=amount,
            note=note,
            occurred_on=on,
            transfer_group_rid=group_rid,
        )
        self._txns.add(
            family_id=dst.family_id,
            wallet_id=dst.id,
            created_by_user_id=user_id,
            type_=TransactionType.TRANSFER_IN,
            amount=amount,
            note=note,
            occurred_on=on,
            transfer_group_rid=group_rid,
        )
        self._session.commit()
        return group_rid, from_wallet_rid, to_wallet_rid, amount, on

    def delete(self, family_id: int | None, user_id: int, group_rid: str) -> None:
        legs = self._txns.list_by_transfer_group(group_rid)
        # Must exist and every leg's wallet must be visible to the caller.
        if not legs or any(
            self._wallets.get_visible_by_rid(family_id, user_id, leg.wallet.rid)
            is None
            for leg in legs
        ):
            raise TransferNotFoundError(group_rid)
        for leg in legs:
            self._txns.delete(leg)
        self._session.commit()
