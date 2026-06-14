"""Family membership logic — stateless. Listing is open to any member;
transferring ownership is owner-only."""

from sqlalchemy.orm import Session

from app.domains.auth.repository import AuthRepository
from app.domains.categories.repository import CategoryRepository
from app.domains.families.repository import FamilyRepository
from app.domains.users.models import User, UserRole


class NotOwnerError(Exception):
    """Raised when a non-owner attempts an owner-only action."""


class AlreadyInFamilyError(Exception):
    """Raised when a user who already belongs to a family tries to create one."""


class MemberNotFoundError(Exception):
    """Raised when the target member is not an active member of the family."""


class CannotTransferToSelfError(Exception):
    """Raised when the owner tries to transfer ownership to themselves."""


class FamilyService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = FamilyRepository(session)
        self._auth = AuthRepository(session)
        self._categories = CategoryRepository(session)

    def create_family(self, current_user: User, name: str) -> User:
        """Create a family for a user who doesn't have one yet, making them its
        owner and seeding the default categories. Returns the updated user (the
        caller reissues the JWT so its family scope is current)."""
        if current_user.family_id is not None:
            raise AlreadyInFamilyError()
        family = self._auth.add_family(name)
        self._categories.seed_defaults(family.id)
        current_user.family_id = family.id
        current_user.role = UserRole.OWNER.value
        self._session.commit()
        self._session.refresh(current_user)
        return current_user

    def list_members(self, family_id: int) -> list[User]:
        return self._repo.list_active_members(family_id)

    def transfer_ownership(
        self, current_user: User, family_id: int, target_rid: str
    ) -> User:
        """Hand ownership to another active member; the old owner becomes a member
        (single-owner model). Returns the new owner."""
        if current_user.role != UserRole.OWNER.value:
            raise NotOwnerError()
        target = self._repo.get_active_member_by_rid(family_id, target_rid)
        if target is None:
            raise MemberNotFoundError(target_rid)
        if target.id == current_user.id:
            raise CannotTransferToSelfError()
        target.role = UserRole.OWNER.value
        current_user.role = UserRole.MEMBER.value
        self._session.commit()
        self._session.refresh(target)
        return target
