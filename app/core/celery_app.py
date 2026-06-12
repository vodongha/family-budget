"""Celery app — broker/backend on Redis. Beat schedules land here from v1.5+."""

from celery import Celery

from app.core.config import settings

celery = Celery(
    "family_budget",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.update(
    task_track_started=True,
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
)
