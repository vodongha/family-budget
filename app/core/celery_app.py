"""Celery app — broker/backend on Redis, plus the account-purge beat schedule."""

from celery import Celery

from app.core.config import settings
from app.core.database import new_session
from app.domains.account.maintenance import purge_expired_accounts

celery = Celery(
    "family_budget",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.update(
    task_track_started=True,
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
    beat_schedule={
        # Daily at 03:00 ICT: permanently purge/anonymise accounts whose
        # soft-deletion is older than the retention window.
        "purge-expired-accounts": {
            "task": "app.purge_expired_accounts",
            "schedule": 24 * 60 * 60.0,
        },
    },
)


@celery.task(name="app.purge_expired_accounts")
def purge_expired_accounts_task() -> dict[str, int]:
    """Celery Beat entry point — wraps the pure purge function in a session."""
    session = new_session()
    try:
        return purge_expired_accounts(session)
    finally:
        session.close()
