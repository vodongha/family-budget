"""DB access for auth — read/write only, no business logic."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.users.models import Family, User, UserRole


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_user_by_email(self, email: str) -> User | None:
        return self._session.scalar(select(User).where(User.email == email))

    def add_family(self, name: str) -> Family:
        family = Family(name=name)
        self._session.add(family)
        self._session.flush()
        return family

    def add_user(
        self,
        email: str,
        hashed_password: str,
        display_name: str,
        family_id: int,
        role: UserRole,
    ) -> User:
        user = User(
            email=email,
            hashed_password=hashed_password,
            display_name=display_name,
            family_id=family_id,
            role=role.value,
        )
        self._session.add(user)
        self._session.flush()
        return user
