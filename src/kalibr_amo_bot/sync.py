from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .config_store import get_mapping
from .kommo import KommoClient
from .models import (
    CallEvent,
    ContactSnapshot,
    DiscoverySample,
    KommoUser,
    LeadSnapshot,
    ReferenceItem,
    SyncCursor,
)


def _dt(value: Any) -> datetime | None:
    if value in (None, 0, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _cursor(db: Session, key: str, lookback_minutes: int, initial_import_days: int = 365) -> int:
    row = db.get(SyncCursor, key)
    if not row:
        return int((datetime.now(UTC) - timedelta(days=initial_import_days)).timestamp())
    try:
        stored = int(row.value)
    except ValueError:
        stored = int((datetime.now(UTC) - timedelta(days=initial_import_days)).timestamp())
    return max(0, stored - lookback_minutes * 60)


def _set_cursor(db: Session, key: str, value: int) -> None:
    row = db.get(SyncCursor, key)
    if row:
        row.value = str(value)
    else:
        db.add(SyncCursor(key=key, value=str(value)))


def _role_group(user: dict[str, Any]) -> tuple[str | None, str | None]:
    embedded = user.get("_embedded", {})
    role = embedded.get("role") or {}
    group = embedded.get("group") or {}
    return role.get("name"), group.get("name")


def sync_users(db: Session, client: KommoClient) -> int:
    seen: set[int] = set()
    count = 0
    for item in client.users():
        user_id = int(item["id"])
        seen.add(user_id)
        rights = item.get("rights") or {}
        role_name, group_name = _role_group(item)
        row = db.get(KommoUser, user_id)
        if not row:
            row = KommoUser(id=user_id, name=str(item.get("name") or user_id))
            db.add(row)
        row.name = str(item.get("name") or user_id)
        row.email = str(item.get("email") or "")
        row.language = str(item.get("lang") or "ru")
        row.is_active = bool(rights.get("is_active", True))
        row.is_admin = bool(rights.get("is_admin", False))
        row.role_id = rights.get("role_id")
        row.role_name = role_name
        row.group_id = rights.get("group_id")
        row.group_name = group_name
        row.raw_json = item
        row.last_verified_at = datetime.now(UTC)
        count += 1
    for row in db.scalars(select(KommoUser)).all():
        if row.id not in seen:
            row.is_active = False
    db.commit()
    return count


def sync_reference_data(db: Session, client: KommoClient) -> int:
    items: list[tuple[str, str, str | None, str, dict[str, Any]]] = []
    for role in client.roles():
        items.append(("role", str(role["id"]), None, str(role.get("name") or role["id"]), role))
    account = client.account()
    for group in account.get("_embedded", {}).get("users_groups", []):
        items.append(("group", str(group["id"]), None, str(group.get("name") or group["id"]), group))
    for task_type in account.get("_embedded", {}).get("task_types", []):
        items.append(("task_type", str(task_type["id"]), None, str(task_type.get("name") or task_type["id"]), task_type))
    for pipeline in client.pipelines():
        pid = str(pipeline["id"])
        items.append(("pipeline", pid, None, str(pipeline.get("name") or pid), pipeline))
        for status in pipeline.get("_embedded", {}).get("statuses", []):
            items.append(("status", str(status["id"]), pid, str(status.get("name") or status["id"]), status))
    for entity_type in ("leads", "contacts"):
        for field in client.custom_fields(entity_type):
            items.append((f"custom_field:{entity_type}", str(field["id"]), None, str(field.get("name") or field["id"]), field))
    for item_type, ext_id, parent, name, raw in items:
        row = db.scalar(select(ReferenceItem).where(ReferenceItem.item_type == item_type, ReferenceItem.external_id == ext_id))
        if not row:
            row = ReferenceItem(item_type=item_type, external_id=ext_id, name=name)
            db.add(row)
        row.parent_external_id = parent
        row.name = name
        row.raw_json = raw
    db.commit()
    return len(items)


def _phone_hashes(item: dict[str, Any], settings: Settings) -> list[str]:
    hashes: list[str] = []
    for field in item.get("custom_fields_values") or []:
        if field.get("field_code") != "PHONE" and field.get("code") != "PHONE":
            continue
        for value in field.get("values") or []:
            raw = re.sub(r"\D+", "", str(value.get("value") or ""))
            if raw:
                hashes.append(hashlib.sha256(f"{settings.phone_hash_salt}:{raw}".encode()).hexdigest())
    return sorted(set(hashes))


def sync_contacts(db: Session, client: KommoClient, settings: Settings) -> int:
    cursor_key = "contacts_updated_at"
    updated_from = _cursor(db, cursor_key, settings.sync_lookback_minutes, settings.initial_import_days)
    maximum = updated_from
    count = 0
    for item in client.contacts(updated_from):
        cid = int(item["id"])
        row = db.get(ContactSnapshot, cid)
        if not row:
            row = ContactSnapshot(kommo_contact_id=cid)
            db.add(row)
        row.responsible_user_id = item.get("responsible_user_id")
        row.kommo_created_at = _dt(item.get("created_at"))
        row.kommo_updated_at = _dt(item.get("updated_at"))
        row.phone_hashes = _phone_hashes(item, settings)
        row.raw_json = item
        maximum = max(maximum, int(item.get("updated_at") or updated_from))
        count += 1
    _set_cursor(db, cursor_key, maximum)
    db.commit()
    return count


def sync_leads(db: Session, client: KommoClient, settings: Settings) -> int:
    cursor_key = "leads_updated_at"
    updated_from = _cursor(db, cursor_key, settings.sync_lookback_minutes, settings.initial_import_days)
    maximum = updated_from
    count = 0
    for item in client.leads(updated_from):
        lid = int(item["id"])
        row = db.get(LeadSnapshot, lid)
        if not row:
            row = LeadSnapshot(kommo_lead_id=lid)
            db.add(row)
        row.responsible_user_id = item.get("responsible_user_id")
        row.pipeline_id = item.get("pipeline_id")
        row.status_id = item.get("status_id")
        row.kommo_created_at = _dt(item.get("created_at"))
        row.kommo_updated_at = _dt(item.get("updated_at"))
        row.linked_contact_ids = [int(x["id"]) for x in item.get("_embedded", {}).get("contacts", []) if x.get("id")]
        row.raw_json = item
        maximum = max(maximum, int(item.get("updated_at") or updated_from))
        count += 1
    _set_cursor(db, cursor_key, maximum)
    db.commit()
    return count


def _text_from_result(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "result", "status", "value", "call_status"):
            if value.get(key) not in (None, ""):
                return str(value[key])
    return ""


def _map_result(raw: str, status_id: int | None, mapping: dict[str, Any]) -> str:
    if status_id is not None:
        if status_id in {int(x) for x in mapping.get("success_status_ids", [])}:
            return "success"
        if status_id in {int(x) for x in mapping.get("failure_status_ids", [])}:
            return "failure"
        if status_id in {int(x) for x in mapping.get("in_progress_status_ids", [])}:
            return "in_progress"
    normalized = raw.casefold()
    for category, key in (("success", "success_patterns"), ("failure", "failure_patterns"), ("in_progress", "in_progress_patterns")):
        if any(str(pattern).casefold() in normalized for pattern in mapping.get(key, []) if str(pattern).strip()):
            return category
    return "no_result"


def _target(db: Session, entity_type: str, entity_id: int | None, raw: dict[str, Any], settings: Settings) -> tuple[int | None, int | None, str, int | None]:
    contact_id: int | None = None
    lead_id: int | None = None
    status_id: int | None = None
    if entity_type in {"contact", "contacts"} and entity_id:
        contact_id = entity_id
    elif entity_type in {"lead", "leads"} and entity_id:
        lead_id = entity_id
        lead = db.get(LeadSnapshot, entity_id)
        if lead:
            status_id = lead.status_id
            if lead.linked_contact_ids:
                contact_id = int(lead.linked_contact_ids[0])
    if contact_id:
        return contact_id, lead_id, f"contact:{contact_id}", status_id
    params = raw.get("params") or {}
    phone = re.sub(r"\D+", "", str(params.get("phone") or params.get("phone_number") or ""))
    if phone:
        digest = hashlib.sha256(f"{settings.phone_hash_salt}:{phone}".encode()).hexdigest()
        return None, lead_id, f"phone:{digest}", status_id
    return None, lead_id, f"{entity_type}:{entity_id or raw.get('id')}", status_id


def _upsert_event(
    db: Session,
    *,
    settings: Settings,
    mapping: dict[str, Any],
    source_type: str,
    source_id: str,
    responsible_user_id: int | None,
    event_at: datetime | None,
    entity_type: str,
    entity_id: int | None,
    raw_result: str,
    duration_seconds: int | None,
    raw: dict[str, Any],
) -> bool:
    if not responsible_user_id or not event_at:
        return False
    minimum = int(mapping.get("minimum_duration_seconds") or 0)
    if minimum and duration_seconds is not None and duration_seconds < minimum:
        return False
    contact_id, lead_id, target_key, status_id = _target(db, entity_type, entity_id, raw, settings)
    category = _map_result(raw_result, status_id, mapping)
    row = db.scalar(select(CallEvent).where(CallEvent.source_type == source_type, CallEvent.source_id == source_id))
    if not row:
        row = CallEvent(source_type=source_type, source_id=source_id, responsible_user_id=responsible_user_id, event_at=event_at, entity_type=entity_type, target_key=target_key)
        db.add(row)
    row.responsible_user_id = responsible_user_id
    row.event_at = event_at
    row.entity_type = entity_type
    row.entity_id = entity_id
    row.contact_id = contact_id
    row.lead_id = lead_id
    row.target_key = target_key
    row.result_category = category
    row.result_raw = raw_result[:500] if raw_result else None
    row.duration_seconds = duration_seconds
    row.raw_json = raw
    return True


def sync_tasks(db: Session, client: KommoClient, settings: Settings) -> int:
    mapping = get_mapping(db)
    if mapping.get("event_source") not in {"tasks", "hybrid"}:
        return 0
    cursor_key = "tasks_updated_at"
    updated_from = _cursor(db, cursor_key, settings.sync_lookback_minutes, settings.initial_import_days)
    maximum = updated_from
    allowed_types = {int(x) for x in mapping.get("task_type_ids", [])}
    count = 0
    for item in client.tasks(updated_from):
        maximum = max(maximum, int(item.get("updated_at") or updated_from))
        task_type_id = item.get("task_type_id")
        if allowed_types and task_type_id not in allowed_types:
            continue
        is_completed = bool(item.get("is_completed"))
        if not is_completed and not mapping.get("include_uncompleted_tasks"):
            continue
        entity_type = str(item.get("entity_type") or "unknown")
        entity_id = item.get("entity_id")
        result = _text_from_result(item.get("result"))
        event_at = _dt(item.get("updated_at") or item.get("complete_till"))
        if _upsert_event(db, settings=settings, mapping=mapping, source_type="task", source_id=str(item["id"]), responsible_user_id=item.get("responsible_user_id"), event_at=event_at, entity_type=entity_type, entity_id=int(entity_id) if entity_id else None, raw_result=result, duration_seconds=None, raw=item):
            count += 1
    _set_cursor(db, cursor_key, maximum)
    db.commit()
    return count


def sync_notes(db: Session, client: KommoClient, settings: Settings) -> int:
    mapping = get_mapping(db)
    if mapping.get("event_source") not in {"notes", "hybrid"}:
        return 0
    note_types = [str(x) for x in mapping.get("note_types", [])]
    count = 0
    for entity_type in mapping.get("call_entity_types", ["contacts", "leads"]):
        cursor_key = f"notes:{entity_type}:updated_at"
        updated_from = _cursor(db, cursor_key, settings.sync_lookback_minutes, settings.initial_import_days)
        maximum = updated_from
        for item in client.notes(entity_type, updated_from, note_types):
            maximum = max(maximum, int(item.get("updated_at") or updated_from))
            params = item.get("params") or {}
            result = _text_from_result(params)
            duration = params.get("duration") or params.get("duration_seconds")
            try:
                duration_int = int(duration) if duration is not None else None
            except (TypeError, ValueError):
                duration_int = None
            if _upsert_event(db, settings=settings, mapping=mapping, source_type=f"note:{entity_type}", source_id=str(item["id"]), responsible_user_id=item.get("responsible_user_id") or item.get("created_by"), event_at=_dt(item.get("created_at")), entity_type=entity_type, entity_id=int(item["entity_id"]) if item.get("entity_id") else None, raw_result=result, duration_seconds=duration_int, raw=item):
                count += 1
        _set_cursor(db, cursor_key, maximum)
    db.commit()
    return count



def _save_sample(db: Session, sample_type: str, item: dict[str, Any]) -> None:
    source_id = str(item.get("id") or hashlib.sha256(repr(item).encode()).hexdigest())
    row = db.scalar(select(DiscoverySample).where(DiscoverySample.sample_type == sample_type, DiscoverySample.source_id == source_id))
    if not row:
        row = DiscoverySample(sample_type=sample_type, source_id=source_id)
        db.add(row)
    row.raw_json = item


def sync_discovery_samples(db: Session, client: KommoClient) -> int:
    """Capture recent raw records without treating them as calls.

    This lets the admin discover the actual task types, note types and result fields
    used by the account before enabling trusted reporting.
    """
    updated_from = int((datetime.now(UTC) - timedelta(days=14)).timestamp())
    count = 0
    for item in client.tasks(updated_from):
        _save_sample(db, "task", item)
        count += 1
        if count >= 100:
            break
    for entity_type in ("contacts", "leads"):
        entity_count = 0
        for item in client.notes(entity_type, updated_from, []):
            _save_sample(db, f"note:{entity_type}", item)
            count += 1
            entity_count += 1
            if entity_count >= 100:
                break
    db.commit()
    return count

def sync_all(db: Session, client: KommoClient, settings: Settings) -> dict[str, int]:
    return {
        "users": sync_users(db, client),
        "references": sync_reference_data(db, client),
        "discovery_samples": sync_discovery_samples(db, client),
        "contacts": sync_contacts(db, client, settings),
        "leads": sync_leads(db, client, settings),
        "tasks": sync_tasks(db, client, settings),
        "notes": sync_notes(db, client, settings),
    }
