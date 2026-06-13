"""DB access for invitations. Family-scoped, except token lookup (used at accept,
before the invitee has any family context)."""

# The repository has a method named ``list``, which shadows the builtin inside the
# class body; deferring annotation evaluation keeps ``list[...]`` hints valid.
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.invitations.models import Invitation, InvitationStatus
from app.domains.users.models import UserRole


class InvitationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        family_id: int,
        email: str | None,
        phone: str | None,
        role: UserRole,
        token: str,
        invited_by_user_id: int,
        target_user_id: int | None = None,
    ) -> Invitation:
        invitation = Invitation(
            family_id=family_id,
            email=email,
            phone=phone,
            role=role.value,
            token=token,
            status=InvitationStatus.PENDING.value,
            invited_by_user_id=invited_by_user_id,
            target_user_id=target_user_id,
        )
        self._session.add(invitation)
        self._session.flush()
        return invitation

    def list(self, family_id: int) -> list[Invitation]:
        stmt = (
            select(Invitation)
            .where(Invitation.family_id == family_id)
            .order_by(Invitation.created_at.desc())
        )
        return list(self._session.scalars(stmt).all())

    def get_by_rid(self, family_id: int, rid: str) -> Invitation | None:
        stmt = select(Invitation).where(
            Invitation.family_id == family_id, Invitation.rid == rid
        )
        return self._session.scalar(stmt)

    def get_by_token(self, token: str) -> Invitation | None:
        return self._session.scalar(select(Invitation).where(Invitation.token == token))

    def pending_for_email(self, family_id: int, email: str) -> Invitation | None:
        stmt = select(Invitation).where(
            Invitation.family_id == family_id,
            Invitation.email == email,
            Invitation.status == InvitationStatus.PENDING.value,
        )
        return self._session.scalar(stmt)

    def pending_for_target(
        self, family_id: int, target_user_id: int
    ) -> Invitation | None:
        stmt = select(Invitation).where(
            Invitation.family_id == family_id,
            Invitation.target_user_id == target_user_id,
            Invitation.status == InvitationStatus.PENDING.value,
        )
        return self._session.scalar(stmt)

    def list_inbox(self, target_user_id: int) -> list[Invitation]:
        """Pending invites addressed to an existing account (the invitee's inbox)."""
        stmt = (
            select(Invitation)
            .where(
                Invitation.target_user_id == target_user_id,
                Invitation.status == InvitationStatus.PENDING.value,
            )
            .order_by(Invitation.created_at.desc())
        )
        return list(self._session.scalars(stmt).all())

    def get_pending_for_target(
        self, target_user_id: int, rid: str
    ) -> Invitation | None:
        stmt = select(Invitation).where(
            Invitation.rid == rid,
            Invitation.target_user_id == target_user_id,
            Invitation.status == InvitationStatus.PENDING.value,
        )
        return self._session.scalar(stmt)
