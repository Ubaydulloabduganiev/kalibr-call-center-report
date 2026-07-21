from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .access import scoped_user_ids
from .config import Settings
from .models import AccessPolicy, DeliveryLog, KommoUser, TelegramIdentity
from .reports import format_report, period_for
from .telegram import TelegramClient


def _time_matches(now_local: datetime, value: str) -> bool:
    hour, minute = [int(x) for x in value.split(":", 1)]
    return now_local.hour == hour and now_local.minute == minute


def _claim(db: Session, user_id: int, kind: str, period_key: str) -> DeliveryLog | None:
    row = DeliveryLog(kommo_user_id=user_id, report_kind=kind, period_key=period_key, status="claimed")
    db.add(row)
    try:
        db.commit()
        return row
    except IntegrityError:
        db.rollback()
        return None


def dispatch_scheduled_reports(db: Session, settings: Settings, now: datetime | None = None) -> int:
    now_local = (now or datetime.now(UTC)).astimezone(ZoneInfo(settings.timezone))
    policies = db.scalars(select(AccessPolicy).where(AccessPolicy.enabled.is_(True), AccessPolicy.receive_scheduled_reports.is_(True), AccessPolicy.access_level != "blocked")).all()
    tg = TelegramClient(settings.telegram_bot_token)
    sent = 0
    for policy in policies:
        user = db.get(KommoUser, policy.kommo_user_id)
        identity = db.scalar(select(TelegramIdentity).where(TelegramIdentity.kommo_user_id == policy.kommo_user_id, TelegramIdentity.revoked_at.is_(None)))
        if not user or not user.is_active or not identity:
            continue
        planned: list[tuple[str, bool, str]] = []
        daily_time = settings.daily_operator_time if policy.access_level == "operator" else settings.daily_manager_time if policy.access_level == "manager" else settings.daily_executive_time
        if _time_matches(now_local, daily_time):
            planned.append(("daily", policy.access_level != "operator", "daily"))
        if now_local.weekday() == settings.weekly_report_weekday and _time_matches(now_local, settings.weekly_report_time):
            planned.append(("weekly", policy.access_level != "operator", "weekly"))
        if now_local.day == 1 and _time_matches(now_local, settings.monthly_report_time):
            planned.append(("monthly", policy.access_level != "operator", "monthly"))
        for kind, team, log_kind in planned:
            period = period_for(kind, settings.timezone, now=now, previous=kind in {"weekly", "monthly"})
            delivery = _claim(db, user.id, log_kind, period.key)
            if not delivery:
                continue
            ids = scoped_user_ids(db, user, policy) if team else [user.id]
            language = policy.language
            title = "Командный отчёт" if language == "ru" and team else "Личный отчёт" if language == "ru" else "Jamoa hisoboti" if team else "Shaxsiy hisobot"
            try:
                tg.send(identity.telegram_chat_id, format_report(db, ids, period, language, title, include_breakdown=team))
                delivery.status = "delivered"
                delivery.delivered_at = datetime.now(UTC)
                db.commit()
                sent += 1
            except Exception as exc:
                # Remove the claim so the next scheduler iteration can retry safely.
                db.delete(delivery)
                db.commit()
    return sent
