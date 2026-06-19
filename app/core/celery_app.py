"""Celery app — broker/backend on Redis, plus the account-purge beat schedule."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings
from app.core.database import new_session
from app.domains.account.maintenance import purge_expired_accounts
from app.domains.rates.tasks import fetch_exchange_rates

celery = Celery(
    "family_budget",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.update(
    task_track_started=True,
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
    # Crontab (fixed clock times) rather than relative intervals: an interval
    # schedule resets its countdown every time the worker restarts (e.g. on each
    # deploy), so frequent deploys could keep pushing the next run indefinitely.
    # Crontab fires at the wall-clock time regardless of when beat started.
    beat_schedule={
        # Daily at 03:00 ICT: permanently purge/anonymise accounts whose
        # soft-deletion is older than the retention window.
        "purge-expired-accounts": {
            "task": "app.purge_expired_accounts",
            "schedule": crontab(hour=3, minute=0),
        },
        # Twice a day (00:00 + 12:00 ICT): refresh currency exchange rates.
        "refresh-exchange-rates": {
            "task": "app.refresh_exchange_rates",
            "schedule": crontab(hour="0,12", minute=0),
        },
    },
)


@celery.task(name="app.refresh_exchange_rates")
def refresh_exchange_rates_task() -> int:
    """Celery Beat entry point — wraps the rate fetch in a session."""
    session = new_session()
    try:
        return fetch_exchange_rates(session)
    finally:
        session.close()


@celery.task(name="app.purge_expired_accounts")
def purge_expired_accounts_task() -> dict[str, int]:
    """Celery Beat entry point — wraps the pure purge function in a session."""
    session = new_session()
    try:
        return purge_expired_accounts(session)
    finally:
        session.close()
