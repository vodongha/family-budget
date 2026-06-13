"""DB access for family membership. Always scoped by ``family_id``."""

from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.domains.users.models import User


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
