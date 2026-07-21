from celery import Celery
from celery.schedules import crontab

from .config import get_settings

settings = get_settings()
celery_app = Celery("kalibr_amo_bot", broker=settings.redis_url, backend=settings.redis_url, include=["kalibr_amo_bot.tasks"])
celery_app.conf.update(
    timezone=settings.timezone,
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "sync-users-every-10-minutes": {"task": "kalibr.sync_users", "schedule": 600.0},
        "sync-activity-every-2-minutes": {"task": "kalibr.sync_activity", "schedule": 120.0},
        "dispatch-reports-every-minute": {"task": "kalibr.dispatch_reports", "schedule": 60.0},
        "recover-telegram-updates": {"task": "kalibr.recover_telegram_updates", "schedule": 60.0},
        "reconcile-nightly": {"task": "kalibr.reconcile", "schedule": crontab(hour=2, minute=15)},
    },
)
