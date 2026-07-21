# Kalibr amoCRM Call-Center Report Bot

A separate, read-only Telegram reporting service for Kalibr Books.

## What it does

- Synchronizes active amoCRM/Kommo users, groups, roles, pipelines, contacts, leads, tasks and notes.
- Allows only explicitly approved, currently active amoCRM users to link Telegram.
- Re-checks amoCRM active status before every bot command, with a five-minute cache.
- Supports operator, manager and executive report scopes.
- Produces daily, weekly and monthly reports.
- Counts total attempts, unique contacts, new contacts, first-time contacts within imported history, success, failure, in-progress, no-result and repeat attempts.
- Never stores amoCRM employee passwords.
- Never stores raw customer phone numbers; only a salted hash may be retained for deduplication.
- Uses configurable adapters because each amoCRM account records calls differently.

## Important data rule

The bot reports only activity that exists in amoCRM. Without telephony, it cannot independently prove that a call happened or lasted ten seconds. Version 1 therefore treats a configured completed task or call note as the call attempt.

## Quick local start

1. Copy `.env.example` to `.env` and fill secrets.
2. Run `docker compose up --build`.
3. Open `http://localhost:10001/admin`.
4. Click **Sync users & discovery**.
5. Approve users and map your call source/results.
6. Run `docker compose exec api kalibr-amo-bot configure-webhook`.
7. In amoCRM Webhooks, use `https://YOUR_API/webhooks/kommo/YOUR_KOMMO_WEBHOOK_SECRET`.

## Telegram commands

- `/today` or `/daily` — current day
- `/weekly` — current week
- `/monthly` — current month
- `/team_today`, `/team_weekly`, `/team_monthly` — manager/executive reports
- `/whoami` — linked amoCRM identity and access level
- `/lang ru` or `/lang uz`
- `/help`

## Access model

- `operator`: own statistics only
- `manager`: users in the same amoCRM group
- `executive`: entire account
- `blocked`: no access

Newly synchronized amoCRM users are denied by default until an administrator enables them in `/admin/users`.

## Configuration-first import

Open `/admin/discovery` after the first sync. It shows pipelines, stages, task types, custom fields and recent sample tasks/notes. Configure the event source and result mappings in `/admin/mapping` before trusting reports.


## Historical accuracy

`INITIAL_IMPORT_DAYS` defaults to 365. Set it higher before the first sync when “first ever called” must consider older history. Existing events outside the imported window cannot be inferred.
