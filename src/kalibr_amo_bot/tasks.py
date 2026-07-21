from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .kommo import KommoClient
from .models import SyncCursor, TelegramUpdate
from .scheduler import dispatch_scheduled_reports
from .sync import sync_contacts, sync_leads, sync_notes, sync_reference_data, sync_tasks, sync_users
from .telegram import process_update
from .worker import celery_app


@celery_app.task(name="kalibr.process_telegram_update", autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def process_telegram_update(update_id: int) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        row = db.get(TelegramUpdate, update_id)
        if not row or row.processed_at:
            return
        if row.processing_at and datetime.now(UTC) - (row.processing_at.replace(tzinfo=UTC) if row.processing_at.tzinfo is None else row.processing_at) < timedelta(minutes=5):
            return
        row.processing_at = datetime.now(UTC)
        db.commit()
        try:
            process_update(db, row.payload_json, settings)
            row.processing_at = None
            row.processed_at = datetime.now(UTC)
            row.error_text = None
            db.commit()
        except Exception as exc:
            row.processing_at = None
            row.error_text = str(exc)[:2000]
            db.commit()
            raise


@celery_app.task(name="kalibr.full_sync")
def full_sync_task() -> dict:
    from .sync import sync_all
    settings = get_settings()
    client = KommoClient(settings)
    try:
        with SessionLocal() as db:
            return sync_all(db, client, settings)
    finally:
        client.close()


@celery_app.task(name="kalibr.sync_users")
def sync_users_task() -> dict:
    settings = get_settings()
    client = KommoClient(settings)
    try:
        with SessionLocal() as db:
            return {"users": sync_users(db, client), "references": sync_reference_data(db, client)}
    finally:
        client.close()


@celery_app.task(name="kalibr.sync_activity")
def sync_activity_task() -> dict:
    settings = get_settings()
    client = KommoClient(settings)
    try:
        with SessionLocal() as db:
            return {"contacts": sync_contacts(db, client, settings), "leads": sync_leads(db, client, settings), "tasks": sync_tasks(db, client, settings), "notes": sync_notes(db, client, settings)}
    finally:
        client.close()


@celery_app.task(name="kalibr.reconcile")
def reconcile_task() -> dict:
    settings = get_settings()
    with SessionLocal() as db:
        rewind = int((datetime.now(UTC) - timedelta(days=7)).timestamp())
        for key in ["contacts_updated_at", "leads_updated_at", "tasks_updated_at", "notes:contacts:updated_at", "notes:leads:updated_at"]:
            row = db.get(SyncCursor, key)
            if row:
                row.value = str(rewind)
        db.commit()
    return sync_activity_task()


@celery_app.task(name="kalibr.dispatch_reports")
def dispatch_reports_task() -> int:
    settings = get_settings()
    with SessionLocal() as db:
        return dispatch_scheduled_reports(db, settings)


@celery_app.task(name="kalibr.recover_telegram_updates")
def recover_telegram_updates_task() -> int:
    queued = 0
    with SessionLocal() as db:
        ids = db.scalars(
            select(TelegramUpdate.update_id)
            .where(TelegramUpdate.processed_at.is_(None))
            .order_by(TelegramUpdate.received_at)
            .limit(100)
        ).all()
    for update_id in ids:
        process_telegram_update.delay(update_id)
        queued += 1
    return queued
