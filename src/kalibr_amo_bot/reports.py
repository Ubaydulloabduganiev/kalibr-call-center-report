from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import CallEvent, ContactSnapshot, KommoUser


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


@dataclass(frozen=True)
class Period:
    start: datetime
    end: datetime
    label_ru: str
    label_uz: str
    key: str


def _local_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)
    end = (datetime.combine(day, time.min, tzinfo=tz) + timedelta(days=1)).astimezone(UTC)
    return start, end


def period_for(kind: str, timezone: str, now: datetime | None = None, previous: bool = False) -> Period:
    tz = ZoneInfo(timezone)
    local = (now or datetime.now(UTC)).astimezone(tz)
    if kind == "daily":
        day = local.date() - timedelta(days=1 if previous else 0)
        start, end = _local_bounds(day, tz)
        return Period(start, end, day.strftime("%d.%m.%Y"), day.strftime("%d.%m.%Y"), day.isoformat())
    if kind == "weekly":
        monday = local.date() - timedelta(days=local.weekday())
        if previous:
            monday -= timedelta(days=7)
        start, _ = _local_bounds(monday, tz)
        _, end = _local_bounds(monday + timedelta(days=6), tz)
        end += timedelta(days=0)
        label = f"{monday:%d.%m}–{monday + timedelta(days=6):%d.%m.%Y}"
        return Period(start, end, label, label, f"{monday.isoformat()}_week")
    first = local.date().replace(day=1)
    if previous:
        first = (first - timedelta(days=1)).replace(day=1)
    next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    start, _ = _local_bounds(first, tz)
    end, _ = _local_bounds(next_month, tz)
    label = first.strftime("%m.%Y")
    return Period(start, end, label, label, f"{first:%Y-%m}")


def _first_call_targets(db: Session, user_ids: list[int]) -> dict[str, datetime]:
    rows = db.execute(
        select(CallEvent.target_key, func.min(CallEvent.event_at)).where(CallEvent.responsible_user_id.in_(user_ids)).group_by(CallEvent.target_key)
    ).all()
    return {str(key): _aware(value) for key, value in rows}


def aggregate(db: Session, user_ids: list[int], period: Period) -> dict:
    if not user_ids:
        return {"total_attempts": 0, "unique_contacts": 0, "new_contacts": 0, "first_time_contacts": 0, "success": 0, "failure": 0, "in_progress": 0, "no_result": 0, "repeat_attempts": 0, "success_rate": 0.0}
    events = db.scalars(
        select(CallEvent).where(CallEvent.responsible_user_id.in_(user_ids), CallEvent.event_at >= period.start, CallEvent.event_at < period.end).order_by(CallEvent.event_at)
    ).all()
    targets = {event.target_key for event in events}
    contact_ids = {event.contact_id for event in events if event.contact_id is not None}
    new_contacts = 0
    if contact_ids:
        new_contacts = int(db.scalar(select(func.count(ContactSnapshot.kommo_contact_id)).where(ContactSnapshot.kommo_contact_id.in_(contact_ids), ContactSnapshot.kommo_created_at >= period.start, ContactSnapshot.kommo_created_at < period.end)) or 0)
    first_map = _first_call_targets(db, user_ids)
    first_time = sum(1 for key in targets if key in first_map and period.start <= first_map[key] < period.end)
    result_counts = {"success": 0, "failure": 0, "in_progress": 0, "no_result": 0}
    for event in events:
        result_counts[event.result_category if event.result_category in result_counts else "no_result"] += 1
    completed = result_counts["success"] + result_counts["failure"]
    return {
        "total_attempts": len(events),
        "unique_contacts": len(targets),
        "new_contacts": new_contacts,
        "first_time_contacts": first_time,
        **result_counts,
        "repeat_attempts": max(0, len(events) - len(targets)),
        "success_rate": round(result_counts["success"] / completed * 100, 1) if completed else 0.0,
    }


def by_user(db: Session, user_ids: list[int], period: Period) -> list[dict]:
    rows: list[dict] = []
    for user_id in user_ids:
        user = db.get(KommoUser, user_id)
        if not user:
            continue
        rows.append({"user_id": user_id, "name": user.name, **aggregate(db, [user_id], period)})
    return sorted(rows, key=lambda x: (x["success"], x["unique_contacts"], x["total_attempts"]), reverse=True)


def format_report(db: Session, user_ids: list[int], period: Period, language: str, title: str, include_breakdown: bool) -> str:
    data = aggregate(db, user_ids, period)
    if language == "uz":
        lines = [f"📊 <b>{title}</b>", f"🗓 {period.label_uz}", "", f"📞 Jami urinishlar: <b>{data['total_attempts']}</b>", f"👤 Noyob kontaktlar: <b>{data['unique_contacts']}</b>", f"🆕 Davrda yaratilgan yangi kontaktlar: <b>{data['new_contacts']}</b>", f"✨ Import qilingan tarixda birinchi marta: <b>{data['first_time_contacts']}</b>", f"✅ Muvaffaqiyatli: <b>{data['success']}</b>", f"❌ Muvaffaqiyatsiz: <b>{data['failure']}</b>", f"⏳ Jarayonda: <b>{data['in_progress']}</b>", f"⚠️ Natijasiz: <b>{data['no_result']}</b>", f"🔁 Takroriy urinishlar: <b>{data['repeat_attempts']}</b>", f"📈 Muvaffaqiyat darajasi: <b>{data['success_rate']}%</b>"]
        breakdown_title = "Xodimlar kesimida"
    else:
        lines = [f"📊 <b>{title}</b>", f"🗓 {period.label_ru}", "", f"📞 Всего попыток: <b>{data['total_attempts']}</b>", f"👤 Уникальных контактов: <b>{data['unique_contacts']}</b>", f"🆕 Новых контактов, созданных за период: <b>{data['new_contacts']}</b>", f"✨ Впервые в импортированной истории: <b>{data['first_time_contacts']}</b>", f"✅ Успешно: <b>{data['success']}</b>", f"❌ Неуспешно: <b>{data['failure']}</b>", f"⏳ В процессе: <b>{data['in_progress']}</b>", f"⚠️ Без результата: <b>{data['no_result']}</b>", f"🔁 Повторных попыток: <b>{data['repeat_attempts']}</b>", f"📈 Успешность: <b>{data['success_rate']}%</b>"]
        breakdown_title = "По сотрудникам"
    if include_breakdown:
        lines.extend(["", f"<b>{breakdown_title}:</b>"])
        for i, row in enumerate(by_user(db, user_ids, period), 1):
            lines.append(f"{i}. {row['name']} — 📞 {row['total_attempts']} · 👤 {row['unique_contacts']} · ✅ {row['success']} · ❌ {row['failure']} · ⏳ {row['in_progress']}")
    return "\n".join(lines)[:4000]
