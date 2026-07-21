from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import AppConfig

DEFAULT_MAPPING: dict[str, Any] = {
    "event_source": "hybrid",
    "task_type_ids": [],
    "note_types": ["call_out"],
    "success_status_ids": [],
    "failure_status_ids": [],
    "in_progress_status_ids": [],
    "success_patterns": ["success", "успех", "успеш", "дозвонился", "связались"],
    "failure_patterns": ["fail", "неуспех", "отказ", "не ответил", "не дозвонился", "wrong number"],
    "in_progress_patterns": ["progress", "в работе", "перезвон", "думает", "ожидание"],
    "minimum_duration_seconds": 0,
    "include_uncompleted_tasks": False,
    "call_entity_types": ["contacts", "leads"],
}


def get_config(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(AppConfig, key)
    return row.value_json if row else default


def set_config(db: Session, key: str, value: Any) -> None:
    row = db.get(AppConfig, key)
    if row:
        row.value_json = value
    else:
        db.add(AppConfig(key=key, value_json=value))
    db.commit()


def get_mapping(db: Session) -> dict[str, Any]:
    value = get_config(db, "mapping", DEFAULT_MAPPING)
    return {**DEFAULT_MAPPING, **(value or {})}
