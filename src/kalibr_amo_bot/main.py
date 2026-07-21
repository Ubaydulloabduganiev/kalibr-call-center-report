from __future__ import annotations

from urllib.parse import parse_qs
from pathlib import Path
import secrets

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .admin import router as admin_router
from .config import get_settings
from .db import engine, get_db
from .models import TelegramUpdate, WebhookEvent
from .tasks import process_telegram_update

settings = get_settings()
app = FastAPI(title=settings.app_name, version=settings.app_version)
app.add_middleware(SessionMiddleware, secret_key=settings.admin_session_secret, https_only=settings.app_env == "production", same_site="lax")
app.include_router(admin_router)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parents[2] / "static")), name="static")


@app.get("/")
def root():
    return RedirectResponse("/admin")


@app.get("/health/live")
def live():
    return {"status": "live", "version": settings.app_version}


@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready", "version": settings.app_version}


@app.post("/webhooks/telegram")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != settings.telegram_webhook_secret:
        raise HTTPException(403, "Invalid Telegram secret")
    payload = await request.json()
    update_id = int(payload.get("update_id", 0))
    if not update_id:
        raise HTTPException(400, "Missing update_id")
    try:
        db.add(TelegramUpdate(update_id=update_id, payload_json=payload))
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"ok": True, "duplicate": True}
    try:
        process_telegram_update.delay(update_id)
    except Exception:
        # The update remains durable in PostgreSQL and the recovery task will enqueue it.
        pass
    return {"ok": True}


@app.post("/webhooks/kommo/{secret_token}")
async def kommo_webhook(secret_token: str, request: Request, db: Session = Depends(get_db)):
    if not secrets.compare_digest(secret_token, settings.kommo_webhook_secret):
        raise HTTPException(403, "Invalid Kommo webhook secret")
    body = (await request.body()).decode("utf-8", errors="replace")
    parsed = {key: values if len(values) > 1 else values[0] for key, values in parse_qs(body).items()}
    db.add(WebhookEvent(payload_json=parsed))
    db.commit()
    from .tasks import sync_activity_task
    sync_activity_task.delay()
    return {"ok": True}


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    return JSONResponse({"error": "internal_error", "detail": str(exc) if settings.app_env != "production" else "Internal error"}, status_code=500)
