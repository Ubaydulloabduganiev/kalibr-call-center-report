from datetime import UTC, datetime, timedelta
import hashlib

from kalibr_amo_bot.models import AccessPolicy, KommoUser, LinkToken
from kalibr_amo_bot.telegram import consume_link


def test_one_time_link(db):
    user = KommoUser(id=1, name="A", is_active=True)
    db.add(user)
    db.add(AccessPolicy(kommo_user_id=1, enabled=True, access_level="operator"))
    raw = "secret"
    db.add(LinkToken(kommo_user_id=1, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=datetime.now(UTC)+timedelta(minutes=5)))
    db.commit()
    linked = consume_link(db, raw, 100, 100, "test")
    assert linked.id == 1
