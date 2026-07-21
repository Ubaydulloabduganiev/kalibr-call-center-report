from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .config_store import get_mapping, set_config
from .db import get_db
from .kommo import KommoClient
from .models import AccessPolicy, CallEvent, DiscoverySample, KommoUser, ReferenceItem, TelegramIdentity
from .telegram import create_link

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))


def _require_admin(request: Request) -> None:
    if not request.session.get("admin"):
        raise HTTPException(status_code=401, detail="Authentication required")


def _csrf(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(24)
        request.session["csrf"] = token
    return token


def _check_csrf(request: Request, value: str) -> None:
    if not value or not secrets.compare_digest(value, str(request.session.get("csrf") or "")):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, username: Annotated[str, Form()], password: Annotated[str, Form()], settings: Settings = Depends(get_settings)):
    if secrets.compare_digest(username, settings.admin_username) and secrets.compare_digest(password, settings.admin_password):
        request.session["admin"] = username
        request.session["csrf"] = secrets.token_urlsafe(24)
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": "Invalid credentials"}, status_code=401)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(request, "dashboard.html", {
        "flash": flash,
        "csrf": _csrf(request),
        "users": db.scalar(select(func.count(KommoUser.id))) or 0,
        "active_users": db.scalar(select(func.count(KommoUser.id)).where(KommoUser.is_active.is_(True))) or 0,
        "linked": db.scalar(select(func.count(TelegramIdentity.id)).where(TelegramIdentity.revoked_at.is_(None))) or 0,
        "events": db.scalar(select(func.count(CallEvent.id))) or 0,
    })


@router.post("/sync")
def sync_now(request: Request, csrf: Annotated[str, Form()], db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    _require_admin(request); _check_csrf(request, csrf)
    from .tasks import full_sync_task
    job = full_sync_task.delay()
    request.session["flash"] = f"Full sync queued: {job.id}"
    return RedirectResponse("/admin", status_code=303)


@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    users = db.scalars(select(KommoUser).order_by(KommoUser.is_active.desc(), KommoUser.name)).all()
    return templates.TemplateResponse(request, "users.html", {"users": users, "csrf": _csrf(request)})


@router.post("/users/{user_id}/policy")
def save_policy(request: Request, user_id: int, csrf: Annotated[str, Form()], enabled: Annotated[str | None, Form()] = None, access_level: Annotated[str, Form()] = "blocked", language: Annotated[str, Form()] = "ru", managed_user_ids: Annotated[str, Form()] = "", receive_scheduled_reports: Annotated[str | None, Form()] = None, db: Session = Depends(get_db)):
    _require_admin(request); _check_csrf(request, csrf)
    user = db.get(KommoUser, user_id)
    if not user:
        raise HTTPException(404)
    policy = db.scalar(select(AccessPolicy).where(AccessPolicy.kommo_user_id == user_id))
    if not policy:
        policy = AccessPolicy(kommo_user_id=user_id)
        db.add(policy)
    policy.enabled = enabled == "on"
    policy.access_level = access_level if access_level in {"blocked", "operator", "manager", "executive"} else "blocked"
    policy.language = language if language in {"ru", "uz"} else "ru"
    policy.receive_scheduled_reports = receive_scheduled_reports == "on"
    policy.managed_user_ids = [int(x.strip()) for x in managed_user_ids.split(",") if x.strip().isdigit()]
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/link", response_class=HTMLResponse)
def generate_link(request: Request, user_id: int, csrf: Annotated[str, Form()], db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    _require_admin(request); _check_csrf(request, csrf)
    user = db.get(KommoUser, user_id)
    if not user:
        raise HTTPException(404)
    policy = db.scalar(select(AccessPolicy).where(AccessPolicy.kommo_user_id == user_id))
    if not user.is_active or not policy or not policy.enabled or policy.access_level == "blocked":
        raise HTTPException(400, "Enable an access policy first")
    link = create_link(db, user, settings)
    return templates.TemplateResponse(request, "link.html", {"user": user, "link": link})


@router.post("/users/{user_id}/revoke")
def revoke_link(request: Request, user_id: int, csrf: Annotated[str, Form()], db: Session = Depends(get_db)):
    _require_admin(request); _check_csrf(request, csrf)
    identity = db.scalar(select(TelegramIdentity).where(TelegramIdentity.kommo_user_id == user_id))
    if identity:
        from datetime import UTC, datetime
        identity.revoked_at = datetime.now(UTC)
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/mapping", response_class=HTMLResponse)
def mapping_page(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    return templates.TemplateResponse(request, "mapping.html", {"mapping": get_mapping(db), "csrf": _csrf(request)})


def _ids(value: str) -> list[int]:
    return [int(x.strip()) for x in value.split(",") if x.strip().isdigit()]


def _patterns(value: str) -> list[str]:
    return [x.strip() for x in value.splitlines() if x.strip()]


@router.post("/mapping")
def mapping_save(request: Request, csrf: Annotated[str, Form()], event_source: Annotated[str, Form()], task_type_ids: Annotated[str, Form()] = "", note_types: Annotated[str, Form()] = "", success_status_ids: Annotated[str, Form()] = "", failure_status_ids: Annotated[str, Form()] = "", in_progress_status_ids: Annotated[str, Form()] = "", success_patterns: Annotated[str, Form()] = "", failure_patterns: Annotated[str, Form()] = "", in_progress_patterns: Annotated[str, Form()] = "", minimum_duration_seconds: Annotated[int, Form()] = 0, db: Session = Depends(get_db)):
    _require_admin(request); _check_csrf(request, csrf)
    mapping = {
        "event_source": event_source if event_source in {"tasks", "notes", "hybrid"} else "hybrid",
        "task_type_ids": _ids(task_type_ids),
        "note_types": [x.strip() for x in note_types.split(",") if x.strip()],
        "success_status_ids": _ids(success_status_ids),
        "failure_status_ids": _ids(failure_status_ids),
        "in_progress_status_ids": _ids(in_progress_status_ids),
        "success_patterns": _patterns(success_patterns),
        "failure_patterns": _patterns(failure_patterns),
        "in_progress_patterns": _patterns(in_progress_patterns),
        "minimum_duration_seconds": max(0, minimum_duration_seconds),
        "include_uncompleted_tasks": False,
        "call_entity_types": ["contacts", "leads"],
    }
    set_config(db, "mapping", mapping)
    return RedirectResponse("/admin/mapping", status_code=303)


@router.get("/discovery", response_class=HTMLResponse)
def discovery_page(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    refs = db.scalars(select(ReferenceItem).order_by(ReferenceItem.item_type, ReferenceItem.name)).all()
    samples = db.scalars(select(DiscoverySample).order_by(DiscoverySample.updated_at.desc()).limit(100)).all()
    events = db.scalars(select(CallEvent).order_by(CallEvent.event_at.desc()).limit(20)).all()
    return templates.TemplateResponse(request, "discovery.html", {"refs": refs, "samples": samples, "events": events, "json": json})
