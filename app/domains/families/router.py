"""Family membership routes. Listing members is open to any member of the family;
transferring ownership is owner-only."""

from fastapi import APIRouter, HTTPException, Response, status

from app.core.deps import CurrentFamily, CurrentUser, SessionDep
from app.core.security import create_access_token
from app.domains.auth.schemas import Token
from app.domains.families.schemas import (
    CreateFamilyRequest,
    FamilyRead,
    FamilyUpdate,
    MemberRead,
    TransferOwnershipRequest,
)
from app.domains.families.service import (
    AlreadyInFamilyError,
    CannotRemoveSelfError,
    CannotTransferToSelfError,
    FamilyService,
    MemberNotFoundError,
    MustTransferFirstError,
    NotOwnerError,
    NotSoleMemberError,
)

router = APIRouter(tags=["family"])

_NOT_OWNER = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="Only the family owner can do this"
)


def _token_for(user) -> Token:  # type: ignore[no-untyped-def]
    return Token(
        access_token=create_access_token(
            subject=user.rid, extra={"family_id": user.family_id}
        )
    )


@router.post(
    "/families",
    response_model=Token,
    status_code=status.HTTP_201_CREATED,
    summary="Create my family",
)
def create_family(
    payload: CreateFamilyRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> Token:
    """Create a family for the signed-in account and make it the **owner**
    (seeding default categories). For an account with no family yet — e.g. just
    after registering or a first Google sign-in. Returns a fresh JWT carrying the
    new family scope. `409` if you already belong to a family."""
    try:
        user = FamilyService(session).create_family(current_user, payload.name.strip())
    except AlreadyInFamilyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already belong to a family",
        ) from None
    return _token_for(user)


@router.patch("/families", response_model=FamilyRead, summary="Rename my family")
def rename_family(
    payload: FamilyUpdate,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> FamilyRead:
    """Rename the family (owner-only)."""
    try:
        name = FamilyService(session).rename(
            current_user, family_id, payload.name.strip()
        )
    except NotOwnerError:
        raise _NOT_OWNER from None
    return FamilyRead(name=name)


@router.delete("/families", response_model=Token, summary="Delete my family")
def delete_family(
    session: SessionDep, family_id: CurrentFamily, current_user: CurrentUser
) -> Token:
    """Delete the family and all its **shared** data (owner-only, only when no
    other members remain). Personal data is kept; you return to the personal-only
    space. Returns a fresh JWT (no family scope). `409` if other members remain."""
    try:
        user = FamilyService(session).delete_family(current_user, family_id)
    except NotOwnerError:
        raise _NOT_OWNER from None
    except NotSoleMemberError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Remove the other members before deleting the family",
        ) from None
    return _token_for(user)


@router.post("/families/leave", response_model=Token, summary="Leave my family")
def leave_family(session: SessionDep, current_user: CurrentUser) -> Token:
    """Leave the family (your personal data stays). An owner with other members
    must transfer ownership first (`409`). Returns a fresh JWT (no family scope)."""
    try:
        user = FamilyService(session).leave(current_user)
    except MustTransferFirstError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transfer ownership before leaving the family",
        ) from None
    return _token_for(user)


@router.delete(
    "/families/members/{rid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member (owner-only)",
)
def remove_member(
    rid: str,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> Response:
    """Remove another member from the family (owner-only; their personal data
    stays). `404` if not an active member, `400` if you target yourself."""
    try:
        FamilyService(session).remove_member(current_user, family_id, rid)
    except NotOwnerError:
        raise _NOT_OWNER from None
    except MemberNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in this family",
        ) from None
    except CannotRemoveSelfError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use leave or transfer ownership instead",
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/members",
    response_model=list[MemberRead],
    summary="List family members",
)
def list_members(
    session: SessionDep, family_id: CurrentFamily, current_user: CurrentUser
) -> list[MemberRead]:
    """Active members of your family, each with their role. Open to any member."""
    members = FamilyService(session).list_members(family_id)
    return [MemberRead.model_validate(m) for m in members]


@router.post(
    "/families/transfer-ownership",
    response_model=MemberRead,
    summary="Transfer ownership (owner-only)",
)
def transfer_ownership(
    payload: TransferOwnershipRequest,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> MemberRead:
    """Hand ownership to another active member; the caller becomes a member
    (single-owner model). `403` if not the owner, `404` if the target isn't in
    the family, `400` if you target yourself."""
    try:
        new_owner = FamilyService(session).transfer_ownership(
            current_user, family_id, payload.target_rid
        )
    except NotOwnerError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the family owner can transfer ownership",
        ) from None
    except MemberNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in this family",
        ) from None
    except CannotTransferToSelfError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already own this family",
        ) from None
    return MemberRead.model_validate(new_owner)
