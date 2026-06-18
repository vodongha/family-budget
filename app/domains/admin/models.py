"""Admin audit log ORM model.

Every mutating action performed through the ``/admin`` panel writes one row here,
so privileged changes are always attributable and reviewable. Append-only by
convention — the panel never edits or deletes these rows.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Identity, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domains.users.models import new_rid


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    rid: Mapped[str] = mapped_column(String(26), unique=True, default=new_rid)
    # The admin who performed the action. Nullable + ON DELETE SET NULL so the
    # history outlives the actor's account.
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # A dotted verb, e.g. "user.soft_delete", "family.restore", "rates.refresh".
    action: Mapped[str] = mapped_column(String(60))
    # What the action targeted (e.g. "user", "family"); null for global actions.
    target_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_rid: Mapped[str | None] = mapped_column(String(26), nullable=True)
    # Free-form JSON detail (before/after values, reason, …). CLOB on Oracle.
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
