"""Invitation business logic — stateless. Owner-only management; public accept
for new accounts, in-app accept for existing ones."""

# The service has a method named ``list`` (shadows the builtin in the class body);
# deferring annotation evaluation keeps ``list[...]`` hints valid.
from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.phone import try_normalize_phone
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
    """Raised when a pending invitation for the same recipient already exists."""


class MissingEmailError(Exception):
    """Raised when accepting a phone-only invite without supplying an email."""


class AlreadyMemberError(Exception):
    """Raised when the invited account already belongs to this family."""


class MustTransferOwnershipFirstError(Exception):
    """An owner with other members must transfer ownership before leaving."""


class InvitationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = InvitationRepository(session)
        self._auth = AuthRepository(session)

    @staticmethod
    def _require_owner(current_user: User) -> None:
        if current_user.role != UserRole.OWNER.value:
            raise NotOwnerError()

    def _find_existing_target(
        self, family_id: int, email: str | None, phone: str | None
    ) -> User | None:
        """Match the invited contact to an existing account, if any.

        Raises [AlreadyMemberError] when the match is already in this family.
        """
        user = self._auth.get_user_by_email(email) if email is not None else None
        if user is None and phone:
            normalized = try_normalize_phone(phone)
            if normalized is not None:
                user = self._auth.get_user_by_phone(normalized)
        if user is None:
            return None
        if user.family_id == family_id:
            raise AlreadyMemberError(user.rid)
        return user

    def create(
        self,
        current_user: User,
        family_id: int,
        email: str | None,
        phone: str | None,
        role: UserRole,
    ) -> Invitation:
        # Any active family member can invite others. Only an owner may grant a
        # non-member role; everyone else can only invite plain members (the
        # single-owner model means ownership moves via transfer, not invites).
        if current_user.role != UserRole.OWNER.value:
            role = UserRole.MEMBER
        target = self._find_existing_target(family_id, email, phone)
        if target is not None:
            # Existing account → in-app invite, no link.
            if self._repo.pending_for_target(family_id, target.id) is not None:
                raise DuplicateInvitationError(target.rid)
            token = secrets.token_urlsafe(32)
            invitation = self._repo.add(
                family_id, email, phone, role, token, current_user.id,
                target_user_id=target.id,
            )
            self._session.commit()
            return invitation
        # New account → shareable registration link.
        if email is not None and self._repo.pending_for_email(family_id, email):
            raise DuplicateInvitationError(email)
        token = secrets.token_urlsafe(32)
        invitation = self._repo.add(
            family_id, email, phone, role, token, current_user.id
        )
        self._session.commit()
        return invitation

    def get_public(self, token: str) -> tuple[Invitation, str]:
        """For the invite landing page: the invitation + its family name. Public."""
        invitation = self._repo.get_by_token(token)
        if (
            invitation is None
            or invitation.status != InvitationStatus.PENDING.value
        ):
            raise InvitationNotFoundError(token)
        family = self._auth.get_family(invitation.family_id)
        family_name = family.name if family is not None else ""
        return invitation, family_name

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
        self, token: str, password: str, display_name: str, email: str | None = None
    ) -> tuple[User, str]:
        """Accept a link invitation: create the invitee's user in the family, return
        the user and a fresh JWT (auto-login). For phone-only invites the invitee
        supplies their own email."""
        invitation = self._repo.get_by_token(token)
        if invitation is None or invitation.status != InvitationStatus.PENDING.value:
            raise InvitationNotFoundError(token)
        final_email = (invitation.email or email or "").strip().lower()
        if not final_email:
            raise MissingEmailError()
        if self._auth.get_user_by_email(final_email) is not None:
            raise EmailAlreadyRegisteredError(final_email)
        user = self._auth.add_user(
            email=final_email,
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

    def inbox(self, user: User) -> list[tuple[Invitation, str, str]]:
        """Pending in-app invites for ``user`` as (invitation, family_name, inviter)."""
        items: list[tuple[Invitation, str, str]] = []
        for inv in self._repo.list_inbox(user.id):
            family = self._auth.get_family(inv.family_id)
            inviter = self._session.get(User, inv.invited_by_user_id)
            items.append(
                (
                    inv,
                    family.name if family is not None else "",
                    inviter.display_name if inviter is not None else "",
                )
            )
        return items

    def accept_existing(self, user: User, rid: str) -> tuple[User, str]:
        """Accept an in-app invite: move ``user`` into the inviting family. Their
        previous family is soft-deleted if they were its only member; an owner with
        other members must transfer ownership first. Returns the user + a fresh JWT
        (the new family scope)."""
        invitation = self._repo.get_pending_for_target(user.id, rid)
        if invitation is None:
            raise InvitationNotFoundError(rid)

        old_family_id = user.family_id
        others = (
            self._auth.count_active_members(old_family_id, exclude_user_id=user.id)
            if old_family_id is not None
            else 0
        )
        if user.role == UserRole.OWNER.value and old_family_id is not None and others > 0:
            raise MustTransferOwnershipFirstError()

        now = datetime.now(UTC).replace(tzinfo=None)
        user.family_id = invitation.family_id
        user.role = invitation.role
        # If they were the last active member of their old family, tear it down.
        if old_family_id is not None and others == 0:
            old_family = self._auth.get_family(old_family_id)
            if old_family is not None and not old_family.is_deleted:
                old_family.is_deleted = True
                old_family.deleted_at = now
        invitation.status = InvitationStatus.ACCEPTED.value
        invitation.accepted_at = now
        self._session.commit()
        self._session.refresh(user)
        jwt = create_access_token(subject=user.rid, extra={"family_id": user.family_id})
        return user, jwt

    def decline(self, user: User, rid: str) -> Invitation:
        invitation = self._repo.get_pending_for_target(user.id, rid)
        if invitation is None:
            raise InvitationNotFoundError(rid)
        invitation.status = InvitationStatus.DECLINED.value
        self._session.commit()
        return invitation
