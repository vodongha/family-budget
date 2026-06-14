"""DB access for auth — read/write only, no business logic."""

from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.domains.users.models import Family, User, UserRole


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_user_by_email(self, email: str) -> User | None:
        # Match case-insensitively so a Google sign-in (which always returns a
        # lowercased email) links to an account registered with any casing —
        # i.e. the same person stays one account. Soft-deleted accounts are not
        # authenticatable. Use ``== false()`` (not ``.is_(False)``): Oracle has
        # no native boolean, and ``IS 0`` is invalid SQL there (ORA-00908).
        return self._session.scalar(
            select(User).where(
                func.lower(User.email) == email.lower(),
                User.is_deleted == false(),
            )
        )

    def get_user_by_google_sub(self, google_sub: str) -> User | None:
        return self._session.scalar(
            select(User).where(
                User.google_sub == google_sub, User.is_deleted == false()
            )
        )

    def get_user_by_phone(self, phone: str) -> User | None:
        return self._session.scalar(
            select(User).where(User.phone == phone, User.is_deleted == false())
        )

    def get_family(self, family_id: int) -> Family | None:
        return self._session.get(Family, family_id)

    def count_active_members(self, family_id: int, *, exclude_user_id: int) -> int:
        """Active (non-deleted) members of a family, excluding one user."""
        return self._session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.family_id == family_id,
                User.is_deleted == false(),
                User.id != exclude_user_id,
            )
        ) or 0

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
        family_id: int | None,
        role: UserRole,
        google_sub: str | None = None,
        phone: str | None = None,
    ) -> User:
        user = User(
            email=email,
            hashed_password=hashed_password,
            display_name=display_name,
            family_id=family_id,
            role=role.value,
            google_sub=google_sub,
            phone=phone,
        )
        self._session.add(user)
        self._session.flush()
        return user
