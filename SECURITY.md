# Security notes

- Store the Telegram token, Kommo token, webhook secrets, database URL and admin password only in deployment environment variables.
- The Kommo long-lived token has administrator-level impact. Rotate it immediately if exposed.
- Use a unique random secret in the Kommo webhook URL and Telegram `secret_token` header.
- Customer phone numbers are not stored in plaintext. The optional deduplication value is a salted SHA-256 hash.
- One amoCRM user can link to one Telegram identity, and one Telegram identity can link to one amoCRM user.
- Link tokens are hashed, one-use and short-lived.
- Only private Telegram chats are accepted.
- New amoCRM users are blocked by default.
- Deactivate access in amoCRM and revoke the Telegram identity when a staff member leaves.
- Keep exactly one Celery Beat scheduler.
