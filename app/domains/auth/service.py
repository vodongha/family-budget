"""Auth business logic — stateless; the session is passed in per call."""

from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.domains.auth.repository import AuthRepository
from app.domains.users.models import User


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AuthService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = AuthRepository(session)

    def register(
        self, email: str, password: str, display_name: str, family_name: str
    ) -> User:
        if self._repo.get_user_by_email(email) is not None:
            raise EmailAlreadyRegisteredError(email)
        family = self._repo.add_family(family_name)
        user = self._repo.add_user(
            email=email,
            hashed_password=hash_password(password),
            display_name=display_name,
            family_id=family.id,
        )
        self._session.commit()
        return user

    def authenticate(self, email: str, password: str) -> User:
        user = self._repo.get_user_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError()
        return user

    def issue_token(self, user: User) -> str:
        return create_access_token(
            subject=user.rid, extra={"family_id": user.family_id}
        )
