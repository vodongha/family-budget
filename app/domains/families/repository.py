"""DB access for family membership. Always scoped by ``family_id``."""

from sqlalchemy import delete, false, select
from sqlalchemy.orm import Session

from app.domains.budgets.models import Budget
from app.domains.categories.models import Category
from app.domains.invitations.models import Invitation
from app.domains.transactions.models import Transaction
from app.domains.users.models import Family, User
from app.domains.wallets.models import Wallet


class FamilyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_active_members(self, family_id: int) -> list[User]:
        stmt = (
            select(User)
            .where(User.family_id == family_id, User.is_deleted == false())
            .order_by(User.created_at)
        )
        return list(self._session.scalars(stmt).all())

    def get_active_member_by_rid(self, family_id: int, rid: str) -> User | None:
        stmt = select(User).where(
            User.family_id == family_id,
            User.rid == rid,
            User.is_deleted == false(),
        )
        return self._session.scalar(stmt)

    def purge_family(self, family_id: int) -> None:
        """Hard-delete a family and all its **shared** data, children first to
        satisfy FKs. Personal wallets/transactions (``family_id`` null) are not
        touched. Members are detached by the caller; the caller commits."""
        self._session.execute(
            delete(Transaction).where(Transaction.family_id == family_id)
        )
        self._session.execute(delete(Budget).where(Budget.family_id == family_id))
        self._session.execute(delete(Category).where(Category.family_id == family_id))
        self._session.execute(delete(Wallet).where(Wallet.family_id == family_id))
        self._session.execute(
            delete(Invitation).where(Invitation.family_id == family_id)
        )
        self._session.execute(delete(Family).where(Family.id == family_id))
