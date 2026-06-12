"""Invitation business logic — stateless. Owner-only management; public accept."""

import secrets

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.domains.auth.repository import AuthRepository
from app.domains.auth.service import EmailAlreadyRegisteredError
from app.domains.invitations.models import Invitation, InvitationStatus
from app.domains.invitations.repository import InvitationRepository
from app.domains.users.models import User, UserRole


class NotOwnerError(Exception):
    """Raised when a non-owner attempts to manage invitations."""


class InvitationNotFoundError(Exception):
    """Raised when an invitation rid/token is unknown or no longer pending."""


class InvitationNotPendingError(Exception):
    """Raised when revoking an invitation that is already accepted/revoked."""


class DuplicateInvitationError(Exception):
    """Raised when a pending invitation for the same email already exists."""


class InvitationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = InvitationRepository(session)
        self._auth = AuthRepository(session)

    @staticmethod
    def _require_owner(current_user: User) -> None:
        if current_user.role != UserRole.OWNER.value:
            raise NotOwnerError()

    def create(
        self, current_user: User, family_id: int, email: str, role: UserRole
    ) -> Invitation:
        self._require_owner(current_user)
        if self._auth.get_user_by_email(email) is not None:
            raise EmailAlreadyRegisteredError(email)
        if self._repo.pending_for_email(family_id, email) is not None:
            raise DuplicateInvitationError(email)
        token = secrets.token_urlsafe(32)
        invitation = self._repo.add(family_id, email, role, token, current_user.id)
        self._session.commit()
        return invitation

    def list(self, current_user: User, family_id: int) -> list[Invitation]:
        self._require_owner(current_user)
        return self._repo.list(family_id)

    def revoke(self, current_user: User, family_id: int, rid: str) -> Invitation:
        self._require_owner(current_user)
        invitation = self._repo.get_by_rid(family_id, rid)
        if invitation is None:
            raise InvitationNotFoundError(rid)
        if invitation.status != InvitationStatus.PENDING.value:
            raise InvitationNotPendingError(rid)
        invitation.status = InvitationStatus.REVOKED.value
        self._session.commit()
        return invitation

    def accept(
        self, token: str, password: str, display_name: str
    ) -> tuple[User, str]:
        """Accept an invitation: create the invitee's user in the family, return
        the user and a fresh JWT (auto-login)."""
        invitation = self._repo.get_by_token(token)
        if invitation is None or invitation.status != InvitationStatus.PENDING.value:
            raise InvitationNotFoundError(token)
        if self._auth.get_user_by_email(invitation.email) is not None:
            raise EmailAlreadyRegisteredError(invitation.email)
        user = self._auth.add_user(
            email=invitation.email,
            hashed_password=hash_password(password),
            display_name=display_name,
            family_id=invitation.family_id,
            role=UserRole(invitation.role),
        )
        invitation.status = InvitationStatus.ACCEPTED.value
        invitation.accepted_at = func.now()
        self._session.commit()
        jwt = create_access_token(subject=user.rid, extra={"family_id": user.family_id})
        return user, jwt
