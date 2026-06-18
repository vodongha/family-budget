"""Admin panel business logic — stateless; the session is passed in per call.

Reachable only behind ``require_admin``; these methods assume the caller is an
authenticated super-admin.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.domains.admin.models import AdminAuditLog
from app.domains.admin.repository import AdminRepository
from app.domains.users.models import User


class AdminService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = AdminRepository(session)

    def authenticate(self, email: str, password: str) -> User | None:
        """Verify admin credentials. Returns the user only if they are an active
        super-admin with a matching password; otherwise ``None`` (the caller
        shows one generic error, never leaking which check failed)."""
        email = email.strip().lower()
        user = self._session.scalar(
            select(User).where(func.lower(User.email) == email)
        )
        if (
            user is None
            or user.is_deleted
            or not user.is_superadmin
            or not user.hashed_password
            or not verify_password(password, user.hashed_password)
        ):
            return None
        return user

    def get_active_admin(self, rid: str) -> User | None:
        """Load a super-admin by rid, or ``None`` if missing / deleted / no longer
        an admin (so a revoked admin's live session stops working)."""
        user = self._session.scalar(select(User).where(User.rid == rid))
        if user is None or user.is_deleted or not user.is_superadmin:
            return None
        return user

    def dashboard(self) -> dict[str, object]:
        return {
            "metrics": self._repo.metrics(),
            "rates_updated_at": self._repo.latest_rate_updated_at(),
            "recent_audit": self._repo.recent_audit(limit=10),
        }

    def recent_audit(self, limit: int = 50) -> list[AdminAuditLog]:
        return self._repo.recent_audit(limit=limit)

    def log(
        self,
        actor: User,
        action: str,
        *,
        target_type: str | None = None,
        target_rid: str | None = None,
        detail: str | None = None,
    ) -> None:
        """Record an admin action and commit. Call after the mutation succeeds."""
        self._repo.add_audit(
            actor_user_id=actor.id,
            action=action,
            target_type=target_type,
            target_rid=target_rid,
            detail=detail,
        )
        self._session.commit()

    @staticmethod
    def now() -> datetime:
        from datetime import UTC

        return datetime.now(UTC).replace(tzinfo=None)
