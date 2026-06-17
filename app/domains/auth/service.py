"""Auth business logic — stateless; the session is passed in per call."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.google import verify_google_id_token
from app.core.phone import PhoneValidationError, normalize_phone
from app.core.security import create_access_token, hash_password, verify_password
from app.domains.auth.repository import AuthRepository
from app.domains.categories.repository import CategoryRepository
from app.domains.users.models import User, UserRole


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidPhoneError(Exception):
    """The supplied phone number is not a valid, parseable number."""


class PhoneAlreadyInUseError(Exception):
    """The phone number is already attached to another account."""


class OwnerMustTransferError(Exception):
    """An owner with other active members cannot delete until ownership moves."""


class AuthService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = AuthRepository(session)
        self._categories = CategoryRepository(session)

    def _resolve_phone(self, raw: str | None, *, exclude_user_id: int | None) -> str | None:
        """Validate+normalise an optional phone and ensure it's not taken.

        Returns the E.164 form, or ``None`` when no number was supplied.
        """
        if raw is None or not raw.strip():
            return None
        try:
            phone = normalize_phone(raw)
        except PhoneValidationError:
            raise InvalidPhoneError(raw) from None
        existing = self._repo.get_user_by_phone(phone)
        if existing is not None and existing.id != exclude_user_id:
            raise PhoneAlreadyInUseError(phone)
        return phone

    def register(
        self,
        email: str,
        password: str,
        display_name: str,
        family_name: str | None = None,
        phone: str | None = None,
    ) -> User:
        """Create a new account.

        When ``family_name`` is given the account also gets a fresh family it
        **owns** (a convenience path). Otherwise the account starts with no
        family and creates or joins one after first login (``POST /families`` or
        accepting an invitation).
        """
        email = email.strip().lower()
        if self._repo.get_user_by_email(email) is not None:
            raise EmailAlreadyRegisteredError(email)
        normalized_phone = self._resolve_phone(phone, exclude_user_id=None)
        family_id: int | None = None
        role = UserRole.MEMBER
        if family_name and family_name.strip():
            family = self._repo.add_family(family_name.strip())
            self._categories.seed_defaults(family.id)
            family_id = family.id
            role = UserRole.OWNER  # the person who creates the family owns it
        user = self._repo.add_user(
            email=email,
            hashed_password=hash_password(password),
            display_name=display_name,
            family_id=family_id,
            role=role,
            phone=normalized_phone,
        )
        # Seed the personal category set so the personal space is usable at once.
        # (When a family was created above it already has its own seeded set.)
        if family_id is None:
            self._categories.seed_defaults(owner_user_id=user.id)
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
        creates a brand-new account with **no family** (it creates or joins one
        after first login, like password registration). Raises [GoogleAuthError]
        if the token is invalid.
        """
        client_ids = [
            c.strip() for c in settings.google_client_id.split(",") if c.strip()
        ]
        claims = verify_google_id_token(id_token, client_ids)
        google_sub = claims["sub"]
        email = claims["email"].strip().lower()
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

        # Brand-new user — no family yet; they create or join one after sign-in.
        # No password (None, not ""): Oracle coerces '' to NULL and rejects it on
        # a NOT NULL column (ORA-01400). The column is nullable for this reason.
        user = self._repo.add_user(
            email=email,
            hashed_password=None,
            display_name=display_name,
            family_id=None,
            role=UserRole.MEMBER,
            google_sub=google_sub,
        )
        self._categories.seed_defaults(owner_user_id=user.id)
        self._session.commit()
        return user

    def issue_token(self, user: User) -> str:
        return create_access_token(
            subject=user.rid, extra={"family_id": user.family_id}
        )

    def change_password(
        self, user: User, current_password: str | None, new_password: str
    ) -> None:
        """Set or change the account password.

        For an account that already has a password, ``current_password`` must
        match. A Google-only account (no password yet) may set one without a
        current password; afterwards it can also sign in with email + password.
        """
        if user.hashed_password:
            if not current_password or not verify_password(
                current_password, user.hashed_password
            ):
                raise InvalidCredentialsError()
        user.hashed_password = hash_password(new_password)
        self._session.commit()

    def update_profile(
        self, user: User, display_name: str, phone: str | None
    ) -> User:
        """Update the display name and (optional) phone. A blank phone clears it."""
        user.display_name = display_name
        user.phone = self._resolve_phone(phone, exclude_user_id=user.id)
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
