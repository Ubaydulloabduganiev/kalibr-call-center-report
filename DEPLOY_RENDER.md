# Render deployment

Create a separate GitHub repository for this bot. Do not put it inside the existing Kalibr CRM repository.

## Services

1. Web service: `kalibr-amo-report-bot-api`
   - Language: Docker
   - Dockerfile: `Dockerfile`
   - Health check: `/health/ready`

2. Background worker: `kalibr-amo-report-bot-worker`
   - Docker command:
     `celery -A kalibr_amo_bot.worker.celery_app worker --loglevel=INFO --concurrency=2`

3. Scheduler: `kalibr-amo-report-bot-scheduler`
   - Docker command:
     `celery -A kalibr_amo_bot.worker.celery_app beat --loglevel=INFO`
   - Run exactly one scheduler.

4. PostgreSQL database
5. Redis/Key Value service

Copy the same environment variables to the API, worker and scheduler. Use the internal Redis URL for Render services in the same region.

## amoCRM private integration

Create a private integration as an amoCRM administrator and generate a long-lived token. Put it only in Render Environment as `KOMMO_LONG_LIVED_TOKEN`. Never commit it.

## First boot

The API Docker command runs `alembic upgrade head` automatically.

Open `/admin`, sign in with `ADMIN_USERNAME` and `ADMIN_PASSWORD`, then:

1. Sync users and discovery data.
2. Set access levels.
3. Configure call-source/result mapping.
4. Generate Telegram links.
5. Configure webhook from the API Shell:
   `kalibr-amo-bot configure-webhook`
6. In amoCRM Webhooks, add `https://YOUR_API/webhooks/kommo/YOUR_KOMMO_WEBHOOK_SECRET` when your plan supports webhooks. Polling still works without it.
7. Run a 7-day pilot before enabling all operators.
