"""Invitation routes. Management is owner-only; accept is public (invitee has no
account yet)."""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentFamily, CurrentUser, SessionDep
from app.domains.auth.schemas import Token
from app.domains.auth.service import EmailAlreadyRegisteredError
from app.domains.invitations.schemas import (
    AcceptInvitation,
    InvitationCreate,
    InvitationInboxRead,
    InvitationPublic,
    InvitationRead,
)
from app.domains.invitations.service import (
    AlreadyMemberError,
    DuplicateInvitationError,
    InvitationNotFoundError,
    InvitationNotPendingError,
    InvitationService,
    MissingEmailError,
    MustTransferOwnershipFirstError,
    NotOwnerError,
)

router = APIRouter(prefix="/invitations", tags=["invitations"])

_NOT_OWNER = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="Only the family owner can do this"
)


@router.post(
    "",
    response_model=InvitationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Invite someone (owner-only)",
)
def create_invitation(
    payload: InvitationCreate,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> InvitationRead:
    """Invite by email or phone. If the contact already has an account the invite
    is delivered **in-app** (`in_app: true`, no link); otherwise a shareable
    registration link is created. Owner-only (`403`)."""
    try:
        invitation = InvitationService(session).create(
            current_user, family_id, payload.email, payload.phone, payload.role
        )
    except NotOwnerError:
        raise _NOT_OWNER from None
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from None
    except DuplicateInvitationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pending invitation already exists for this person",
        ) from None
    except AlreadyMemberError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That account is already a member of this family",
        ) from None
    return InvitationRead.model_validate(invitation)


@router.get(
    "/inbox",
    response_model=list[InvitationInboxRead],
    summary="My invitation inbox",
)
def list_inbox(session: SessionDep, current_user: CurrentUser) -> list[InvitationInboxRead]:
    """Pending in-app invites addressed to the signed-in account."""
    items = InvitationService(session).inbox(current_user)
    return [
        InvitationInboxRead(
            rid=inv.rid,
            family_name=family_name,
            invited_by=invited_by,
            role=inv.role,
            created_at=inv.created_at,
        )
        for inv, family_name, invited_by in items
    ]


@router.get(
    "",
    response_model=list[InvitationRead],
    summary="List sent invitations (owner-only)",
)
def list_invitations(
    session: SessionDep, family_id: CurrentFamily, current_user: CurrentUser
) -> list[InvitationRead]:
    """Invitations your family has sent. Owner-only (`403`)."""
    try:
        invitations = InvitationService(session).list(current_user, family_id)
    except NotOwnerError:
        raise _NOT_OWNER from None
    return [InvitationRead.model_validate(i) for i in invitations]


@router.get(
    "/{token}",
    response_model=InvitationPublic,
    summary="Read a public invite (no auth)",
)
def get_invitation(token: str, session: SessionDep) -> InvitationPublic:
    """Public: the invite landing page reads this to show the family + whether an
    email is still needed. No auth (the invitee has no account yet)."""
    try:
        invitation, family_name = InvitationService(session).get_public(token)
    except InvitationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found or not pending",
        ) from None
    return InvitationPublic(
        family_name=family_name,
        role=invitation.role,
        status=invitation.status,
        email=invitation.email,
    )


@router.post(
    "/accept",
    response_model=Token,
    summary="Accept an invite as a new user (no auth)",
)
def accept_invitation(payload: AcceptInvitation, session: SessionDep) -> Token:
    """Public: register a brand-new account from an invitation token and join the
    family. Returns a JWT (auto-login). `422` if an email is required, `409` if
    the email is already registered."""
    try:
        _user, jwt = InvitationService(session).accept(
            payload.token, payload.password, payload.display_name, payload.email
        )
    except InvitationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found or not pending",
        ) from None
    except MissingEmailError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="An email is required to accept this invitation",
        ) from None
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from None
    return Token(access_token=jwt)


@router.delete(
    "/{rid}",
    response_model=InvitationRead,
    summary="Revoke an invitation (owner-only)",
)
def revoke_invitation(
    rid: str,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> InvitationRead:
    """Cancel a pending invitation you sent. Owner-only (`403`); `404` if not
    found, `409` if it is no longer pending."""
    try:
        invitation = InvitationService(session).revoke(current_user, family_id, rid)
    except NotOwnerError:
        raise _NOT_OWNER from None
    except InvitationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found"
        ) from None
    except InvitationNotPendingError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Invitation is not pending"
        ) from None
    return InvitationRead.model_validate(invitation)


_INVITE_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Invitation not found or not pending",
)


@router.post(
    "/{rid}/accept-existing",
    response_model=Token,
    summary="Accept an in-app invite",
)
def accept_existing(
    rid: str, session: SessionDep, current_user: CurrentUser
) -> Token:
    """Accept an in-app invite (existing account): join the inviting family in one
    tap. Leaving an owned family with other members is blocked (409)."""
    try:
        _user, jwt = InvitationService(session).accept_existing(current_user, rid)
    except InvitationNotFoundError:
        raise _INVITE_NOT_FOUND from None
    except MustTransferOwnershipFirstError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You own your current family. Transfer ownership to another member "
                "before joining a different family."
            ),
        ) from None
    return Token(access_token=jwt)


@router.post(
    "/{rid}/decline",
    response_model=InvitationInboxRead,
    summary="Decline an in-app invite",
)
def decline(
    rid: str, session: SessionDep, current_user: CurrentUser
) -> InvitationInboxRead:
    """Dismiss a pending in-app invite from your inbox. `404` if not found."""
    try:
        invitation = InvitationService(session).decline(current_user, rid)
    except InvitationNotFoundError:
        raise _INVITE_NOT_FOUND from None
    return InvitationInboxRead(
        rid=invitation.rid,
        family_name="",
        invited_by="",
        role=invitation.role,
        created_at=invitation.created_at,
    )
