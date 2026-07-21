from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .kommo import KommoClient, KommoError
from .models import AccessPolicy, KommoUser, TelegramIdentity


class AccessDenied(RuntimeError):
    pass


def _update_user(row: KommoUser, payload: dict) -> None:
    rights = payload.get("rights") or {}
    embedded = payload.get("_embedded", {})
    row.name = str(payload.get("name") or row.name)
    row.email = str(payload.get("email") or row.email)
    row.is_active = bool(rights.get("is_active", True))
    row.is_admin = bool(rights.get("is_admin", False))
    row.role_id = rights.get("role_id")
    row.group_id = rights.get("group_id")
    row.role_name = (embedded.get("role") or {}).get("name")
    row.group_name = (embedded.get("group") or {}).get("name")
    row.raw_json = payload
    row.last_verified_at = datetime.now(UTC)


def verify_identity(db: Session, telegram_user_id: int, client: KommoClient, settings: Settings) -> tuple[KommoUser, AccessPolicy]:
    identity = db.scalar(select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == telegram_user_id, TelegramIdentity.revoked_at.is_(None)))
    if not identity:
        raise AccessDenied("not_linked")
    user = db.get(KommoUser, identity.kommo_user_id)
    policy = db.scalar(select(AccessPolicy).where(AccessPolicy.kommo_user_id == identity.kommo_user_id))
    if not user or not policy or not policy.enabled or policy.access_level == "blocked":
        raise AccessDenied("not_allowed")
    stale = not user.last_verified_at or datetime.now(UTC) - user.last_verified_at > timedelta(seconds=settings.kommo_user_cache_seconds)
    if stale:
        try:
            payload = client.user(user.id)
            _update_user(user, payload)
            db.commit()
        except KommoError as exc:
            raise AccessDenied("verification_failed") from exc
    if not user.is_active:
        raise AccessDenied("inactive")
    return user, policy


def scoped_user_ids(db: Session, user: KommoUser, policy: AccessPolicy) -> list[int]:
    if policy.access_level == "operator":
        return [user.id]
    if policy.access_level == "executive":
        return list(db.scalars(select(KommoUser.id).where(KommoUser.is_active.is_(True))).all())
    if policy.managed_user_ids:
        return [int(x) for x in policy.managed_user_ids]
    if user.group_id is None:
        return [user.id]
    return list(db.scalars(select(KommoUser.id).where(KommoUser.is_active.is_(True), KommoUser.group_id == user.group_id)).all())
