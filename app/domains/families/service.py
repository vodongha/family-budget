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


class NotSoleMemberError(Exception):
    """Raised when deleting a family that still has other members."""


class MustTransferFirstError(Exception):
    """Raised when an owner with other members tries to leave."""


class CannotRemoveSelfError(Exception):
    """Raised when an owner tries to remove themselves via remove-member."""


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

    def rename(self, current_user: User, family_id: int, name: str) -> str:
        """Rename the family (owner-only). Returns the new name."""
        if current_user.role != UserRole.OWNER.value:
            raise NotOwnerError()
        family = self._auth.get_family(family_id)
        if family is None:
            raise MemberNotFoundError(family_id)
        family.name = name
        self._session.commit()
        return family.name

    def delete_family(self, current_user: User, family_id: int) -> User:
        """Delete the family and all its **shared** data (owner-only, and only
        when no other members remain). Personal data is kept; the owner is
        detached (back to the personal-only space). Returns the updated user."""
        if current_user.role != UserRole.OWNER.value:
            raise NotOwnerError()
        others = self._auth.count_active_members(
            family_id, exclude_user_id=current_user.id
        )
        if others > 0:
            raise NotSoleMemberError()
        current_user.family_id = None
        current_user.role = UserRole.MEMBER.value
        self._session.flush()
        self._repo.purge_family(family_id)
        self._session.commit()
        self._session.refresh(current_user)
        return current_user

    def leave(self, current_user: User) -> User:
        """Leave the current family (keeping personal data). An owner with other
        members must transfer ownership first; a sole member leaving tears the
        (now empty) family down. Returns the updated user."""
        family_id = current_user.family_id
        if family_id is None:
            return current_user
        others = self._auth.count_active_members(
            family_id, exclude_user_id=current_user.id
        )
        if current_user.role == UserRole.OWNER.value and others > 0:
            raise MustTransferFirstError()
        current_user.family_id = None
        current_user.role = UserRole.MEMBER.value
        self._session.flush()
        if others == 0:
            self._repo.purge_family(family_id)
        self._session.commit()
        self._session.refresh(current_user)
        return current_user

    def remove_member(
        self, current_user: User, family_id: int, target_rid: str
    ) -> None:
        """Owner removes another member from the family (their personal data
        stays; they become family-less)."""
        if current_user.role != UserRole.OWNER.value:
            raise NotOwnerError()
        target = self._repo.get_active_member_by_rid(family_id, target_rid)
        if target is None:
            raise MemberNotFoundError(target_rid)
        if target.id == current_user.id:
            raise CannotRemoveSelfError()
        target.family_id = None
        target.role = UserRole.MEMBER.value
        self._session.commit()

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
