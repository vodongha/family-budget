"""Auth business logic — stateless; the session is passed in per call."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.google import verify_google_id_token
from app.core.security import create_access_token, hash_password, verify_password
from app.domains.auth.repository import AuthRepository
from app.domains.users.models import User, UserRole


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class OwnerMustTransferError(Exception):
    """An owner with other active members cannot delete until ownership moves."""


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
        # The person who creates the family owns it.
        user = self._repo.add_user(
            email=email,
            hashed_password=hash_password(password),
            display_name=display_name,
            family_id=family.id,
            role=UserRole.OWNER,
        )
        self._session.commit()
        return user

    def authenticate(self, email: str, password: str) -> User:
        user = self._repo.get_user_by_email(email)
        # Google-only accounts have an empty password hash and cannot password-login.
        if (
            user is None
            or not user.hashed_password
            or not verify_password(password, user.hashed_password)
        ):
            raise InvalidCredentialsError()
        return user

    def google_login(self, id_token: str) -> User:
        """Sign in (or sign up) with a verified Google ID token.

        Links the Google account to an existing user with the same email, or
        creates a new family owned by the new user. Raises [GoogleAuthError] if
        the token is invalid.
        """
        client_ids = [
            c.strip() for c in settings.google_client_id.split(",") if c.strip()
        ]
        claims = verify_google_id_token(id_token, client_ids)
        google_sub = claims["sub"]
        email = claims["email"]
        display_name = claims.get("name") or email.split("@")[0]

        user = self._repo.get_user_by_google_sub(google_sub)
        if user is None:
            user = self._repo.get_user_by_email(email)
        if user is not None:
            # Link Google to this account on first Google sign-in.
            if not user.google_sub:
                user.google_sub = google_sub
            self._session.commit()
            return user

        # Brand-new user — create their family and make them its owner.
        family = self._repo.add_family(f"{display_name}'s Family")
        user = self._repo.add_user(
            email=email,
            hashed_password="",
            display_name=display_name,
            family_id=family.id,
            role=UserRole.OWNER,
            google_sub=google_sub,
        )
        self._session.commit()
        return user

    def issue_token(self, user: User) -> str:
        return create_access_token(
            subject=user.rid, extra={"family_id": user.family_id}
        )

    def update_display_name(self, user: User, display_name: str) -> User:
        user.display_name = display_name
        self._session.commit()
        self._session.refresh(user)
        return user

    def delete_account(self, user: User) -> None:
        """Soft-delete the user's account (Google Play account-deletion policy).

        - An owner with other active members is blocked (must transfer ownership
          first) so a family is never left without an owner.
        - A sole owner also soft-deletes the family, marking all of its data for
          purge by the scheduled job.
        Login and token validation reject the user immediately; a scheduled job
        purges/anonymises the data once the retention window has passed.
        """
        if user.is_deleted:
            return
        # Naive UTC, consistent with the other DateTime columns (func.now()).
        now = datetime.now(UTC).replace(tzinfo=None)
        if user.role == UserRole.OWNER.value and user.family_id is not None:
            others = self._repo.count_active_members(
                user.family_id, exclude_user_id=user.id
            )
            if others > 0:
                raise OwnerMustTransferError()
            # Sole owner — tear down the whole family.
            family = self._repo.get_family(user.family_id)
            if family is not None:
                family.is_deleted = True
                family.deleted_at = now
        user.is_deleted = True
        user.deleted_at = now
        # Unlink Google so the account is no longer reachable via the Google
        # identity and the same Google account can be used again later.
        user.google_sub = None
        self._session.commit()
