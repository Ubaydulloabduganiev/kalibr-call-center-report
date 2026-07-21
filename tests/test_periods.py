from datetime import UTC, datetime
from kalibr_amo_bot.reports import period_for


def test_week_is_monday_to_sunday():
    now = datetime(2026, 7, 22, 12, tzinfo=UTC)
    period = period_for("weekly", "UTC", now)
    assert period.start.date().isoformat() == "2026-07-20"
    assert period.end.date().isoformat() == "2026-07-27"


def test_previous_month():
    now = datetime(2026, 7, 1, 12, tzinfo=UTC)
    period = period_for("monthly", "UTC", now, previous=True)
    assert period.start.date().isoformat() == "2026-06-01"
    assert period.end.date().isoformat() == "2026-07-01"
