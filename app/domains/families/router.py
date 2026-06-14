"""Family membership routes. Listing members is open to any member of the family;
transferring ownership is owner-only."""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentFamily, CurrentUser, SessionDep
from app.core.security import create_access_token
from app.domains.auth.schemas import Token
from app.domains.families.schemas import (
    CreateFamilyRequest,
    MemberRead,
    TransferOwnershipRequest,
)
from app.domains.families.service import (
    AlreadyInFamilyError,
    CannotTransferToSelfError,
    FamilyService,
    MemberNotFoundError,
    NotOwnerError,
)

router = APIRouter(tags=["family"])


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
    return Token(
        access_token=create_access_token(
            subject=user.rid, extra={"family_id": user.family_id}
        )
    )


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
