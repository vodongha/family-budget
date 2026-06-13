"""Family membership routes. Listing members is open to any member of the family;
transferring ownership is owner-only."""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentFamily, CurrentUser, SessionDep
from app.domains.families.schemas import MemberRead, TransferOwnershipRequest
from app.domains.families.service import (
    CannotTransferToSelfError,
    FamilyService,
    MemberNotFoundError,
    NotOwnerError,
)

router = APIRouter(tags=["family"])


@router.get("/members", response_model=list[MemberRead])
def list_members(
    session: SessionDep, family_id: CurrentFamily, current_user: CurrentUser
) -> list[MemberRead]:
    members = FamilyService(session).list_members(family_id)
    return [MemberRead.model_validate(m) for m in members]


@router.post("/families/transfer-ownership", response_model=MemberRead)
def transfer_ownership(
    payload: TransferOwnershipRequest,
    session: SessionDep,
    family_id: CurrentFamily,
    current_user: CurrentUser,
) -> MemberRead:
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
