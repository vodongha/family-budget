"""Invitation routes. Management is owner-only; accept is public (invitee has no
account yet)."""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentFamily, CurrentUser, SessionDep
from app.domains.auth.schemas import Token
from app.domains.auth.service import EmailAlreadyRegisteredError
from app.domains.invitations.schemas import (
    AcceptInvitation,
    InvitationCreate,
    InvitationPublic,
    InvitationRead,
)
from app.domains.invitations.service import (
    DuplicateInvitationError,
    InvitationNotFoundError,
    InvitationNotPendingError,
    InvitationService,
    MissingEmailError,
    NotOwnerError,
)

router = APIRouter(prefix="/invitations", tags=["invitations"])

_NOT_OWNER = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="Only the family owner can do this"
)


@router.post("", response_model=InvitationRead, status_code=status.HTTP_201_CREATED)
def create_invitation(
    payload: InvitationCreate,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> InvitationRead:
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
            detail="A pending invitation already exists for this email",
        ) from None
    return InvitationRead.model_validate(invitation)


@router.get("", response_model=list[InvitationRead])
def list_invitations(
    session: SessionDep, family_id: CurrentFamily, current_user: CurrentUser
) -> list[InvitationRead]:
    try:
        invitations = InvitationService(session).list(current_user, family_id)
    except NotOwnerError:
        raise _NOT_OWNER from None
    return [InvitationRead.model_validate(i) for i in invitations]


@router.get("/{token}", response_model=InvitationPublic)
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


@router.post("/accept", response_model=Token)
def accept_invitation(payload: AcceptInvitation, session: SessionDep) -> Token:
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


@router.delete("/{rid}", response_model=InvitationRead)
def revoke_invitation(
    rid: str,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> InvitationRead:
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
