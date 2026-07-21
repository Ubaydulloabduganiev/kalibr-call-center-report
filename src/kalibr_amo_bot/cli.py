import json

import httpx
import typer
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .kommo import KommoClient
from .models import AccessPolicy, KommoUser, TelegramIdentity
from .reports import format_report, period_for
from .sync import sync_all
from .telegram import TelegramClient, create_link

app = typer.Typer(no_args_is_help=True)


@app.command("configure-webhook")
def configure_webhook() -> None:
    settings = get_settings()
    url = f"{settings.public_base_url.rstrip('/')}/webhooks/telegram"
    response = httpx.post(f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook", json={"url": url, "secret_token": settings.telegram_webhook_secret, "allowed_updates": ["message"]}, timeout=30)
    response.raise_for_status()
    typer.echo(json.dumps(response.json(), indent=2))


@app.command("sync-all")
def sync_all_command() -> None:
    settings = get_settings()
    client = KommoClient(settings)
    try:
        with SessionLocal() as db:
            typer.echo(json.dumps(sync_all(db, client, settings), indent=2))
    finally:
        client.close()


@app.command("create-link")
def create_link_command(email: str = typer.Option(..., help="amoCRM user email")) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        user = db.scalar(select(KommoUser).where(KommoUser.email == email))
        if not user:
            raise typer.BadParameter("User not found; run sync-all first")
        policy = db.scalar(select(AccessPolicy).where(AccessPolicy.kommo_user_id == user.id))
        if not policy or not policy.enabled or policy.access_level == "blocked":
            raise typer.BadParameter("Enable the user's access policy in /admin/users first")
        typer.echo(create_link(db, user, settings))


@app.command("send-report")
def send_report(email: str, kind: str = "daily", team: bool = False) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        user = db.scalar(select(KommoUser).where(KommoUser.email == email))
        if not user or not user.policy or not user.identity:
            raise typer.BadParameter("User, policy or Telegram link missing")
        ids = [user.id]
        if team:
            from .access import scoped_user_ids
            ids = scoped_user_ids(db, user, user.policy)
        period = period_for(kind, settings.timezone)
        text = format_report(db, ids, period, user.policy.language, "Test report", team)
        TelegramClient(settings.telegram_bot_token).send(user.identity.telegram_chat_id, text)
        typer.echo("Sent")


if __name__ == "__main__":
    app()
