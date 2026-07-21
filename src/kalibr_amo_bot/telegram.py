from __future__ import annotations

import hashlib
import html
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .access import AccessDenied, scoped_user_ids, verify_identity
from .config import Settings
from .kommo import KommoClient
from .models import AccessPolicy, AuditLog, KommoUser, LinkToken, TelegramIdentity
from .reports import format_report, period_for


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class TelegramClient:
    def __init__(self, token: str):
        self.base_url = f"https://api.telegram.org/bot{token}"

    def call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(f"{self.base_url}/{method}", json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {data}")
        return data

    def send(self, chat_id: int, text: str, keyboard: dict | None = None) -> None:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text[:4000], "parse_mode": "HTML", "disable_web_page_preview": True}
        if keyboard:
            payload["reply_markup"] = keyboard
        self.call("sendMessage", payload)


def create_link(db: Session, user: KommoUser, settings: Settings) -> str:
    now = datetime.now(UTC)
    for old in db.scalars(select(LinkToken).where(LinkToken.kommo_user_id == user.id, LinkToken.used_at.is_(None), LinkToken.expires_at > now)).all():
        old.expires_at = now
    raw = secrets.token_urlsafe(32)
    db.add(LinkToken(kommo_user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=now + timedelta(minutes=settings.link_token_minutes)))
    db.add(AuditLog(actor="admin", action="telegram.link.created", target=str(user.id)))
    db.commit()
    username = settings.telegram_bot_username.lstrip("@")
    return f"https://t.me/{username}?start={raw}"


def consume_link(db: Session, raw_token: str, telegram_user_id: int, chat_id: int, username: str | None) -> KommoUser:
    now = datetime.now(UTC)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    token = db.scalar(select(LinkToken).where(LinkToken.token_hash == token_hash))
    if not token or token.used_at or _aware(token.expires_at) <= now:
        raise AccessDenied("invalid_link")
    user = db.get(KommoUser, token.kommo_user_id)
    policy = db.scalar(select(AccessPolicy).where(AccessPolicy.kommo_user_id == token.kommo_user_id))
    if not user or not user.is_active or not policy or not policy.enabled or policy.access_level == "blocked":
        raise AccessDenied("not_allowed")
    conflicting = db.scalar(select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == telegram_user_id, TelegramIdentity.kommo_user_id != user.id))
    if conflicting:
        raise AccessDenied("telegram_in_use")
    identity = db.scalar(select(TelegramIdentity).where(TelegramIdentity.kommo_user_id == user.id))
    if not identity:
        identity = TelegramIdentity(kommo_user_id=user.id, telegram_user_id=telegram_user_id, telegram_chat_id=chat_id)
        db.add(identity)
    identity.telegram_user_id = telegram_user_id
    identity.telegram_chat_id = chat_id
    identity.telegram_username = username
    identity.revoked_at = None
    identity.linked_at = now
    token.used_at = now
    db.add(AuditLog(actor=f"telegram:{telegram_user_id}", action="telegram.link.completed", target=str(user.id)))
    db.commit()
    return user


def _messages(language: str) -> dict[str, str]:
    if language == "uz":
        return {
            "help": "<b>Kalibr Call Center Bot</b>\n\n/today — bugungi hisobot\n/weekly — haftalik hisobot\n/monthly — oylik hisobot\n/team_today — jamoa bugun\n/team_weekly — jamoa haftalik\n/team_monthly — jamoa oylik\n/whoami — hisob\n/lang ru yoki /lang uz",
            "not_linked": "Telegram akkauntingiz faol amoCRM foydalanuvchisiga ulanmagan.",
            "denied": "Sizga botdan foydalanishga ruxsat berilmagan yoki amoCRM akkauntingiz faol emas.",
            "linked": "✅ Telegram akkauntingiz amoCRM foydalanuvchisi <b>{name}</b> bilan bog‘landi.",
            "manager_only": "Bu buyruq faqat menejer yoki rahbarlar uchun.",
        }
    return {
        "help": "<b>Kalibr Call Center Bot</b>\n\n/today — отчёт за сегодня\n/weekly — отчёт за неделю\n/monthly — отчёт за месяц\n/team_today — команда сегодня\n/team_weekly — команда за неделю\n/team_monthly — команда за месяц\n/whoami — учётная запись\n/lang ru или /lang uz",
        "not_linked": "Ваш Telegram не связан с активным пользователем amoCRM.",
        "denied": "Доступ к боту не разрешён или ваша учётная запись amoCRM неактивна.",
        "linked": "✅ Telegram связан с пользователем amoCRM <b>{name}</b>.",
        "manager_only": "Команда доступна только руководителям.",
    }


def process_update(db: Session, update: dict[str, Any], settings: Settings) -> None:
    message = update.get("message") or update.get("edited_message")
    if not message or message.get("chat", {}).get("type") != "private":
        return
    chat_id = int(message["chat"]["id"])
    sender = message.get("from") or {}
    telegram_user_id = int(sender["id"])
    text = str(message.get("text") or "").strip()
    tg = TelegramClient(settings.telegram_bot_token)
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            try:
                user = consume_link(db, parts[1], telegram_user_id, chat_id, sender.get("username"))
                language = user.policy.language if user.policy else settings.default_language
                tg.send(chat_id, _messages(language)["linked"].format(name=html.escape(user.name)))
            except AccessDenied:
                tg.send(chat_id, _messages(settings.default_language)["denied"])
        else:
            tg.send(chat_id, _messages(settings.default_language)["not_linked"])
        return
    client = KommoClient(settings)
    try:
        user, policy = verify_identity(db, telegram_user_id, client, settings)
    except AccessDenied as exc:
        key = "not_linked" if str(exc) == "not_linked" else "denied"
        tg.send(chat_id, _messages(settings.default_language)[key])
        return
    finally:
        client.close()
    language = policy.language
    msg = _messages(language)
    command = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
    if command in {"/help", "/start"}:
        tg.send(chat_id, msg["help"])
        return
    if command == "/whoami":
        tg.send(chat_id, f"👤 <b>{html.escape(user.name)}</b>\namoCRM ID: <code>{user.id}</code>\nУровень / Daraja: <b>{policy.access_level}</b>\nГруппа / Guruh: {html.escape(user.group_name or '—')}")
        return
    if command == "/lang":
        parts = text.split(maxsplit=1)
        if len(parts) == 2 and parts[1].lower() in {"ru", "uz"}:
            policy.language = parts[1].lower()
            db.commit()
            tg.send(chat_id, "✅")
        else:
            tg.send(chat_id, "/lang ru | /lang uz")
        return
    mapping = {
        "/today": ("daily", False),
        "/daily": ("daily", False),
        "/weekly": ("weekly", False),
        "/monthly": ("monthly", False),
        "/team_today": ("daily", True),
        "/team_weekly": ("weekly", True),
        "/team_monthly": ("monthly", True),
    }
    if command not in mapping:
        tg.send(chat_id, msg["help"])
        return
    kind, team = mapping[command]
    if team and policy.access_level not in {"manager", "executive"}:
        tg.send(chat_id, msg["manager_only"])
        return
    ids = scoped_user_ids(db, user, policy) if team else [user.id]
    period = period_for(kind, settings.timezone)
    title = "Командный отчёт" if language == "ru" and team else "Личный отчёт" if language == "ru" else "Jamoa hisoboti" if team else "Shaxsiy hisobot"
    tg.send(chat_id, format_report(db, ids, period, language, title, include_breakdown=team))
