from datetime import UTC, datetime

from kalibr_amo_bot.models import CallEvent, ContactSnapshot, KommoUser
from kalibr_amo_bot.reports import Period, aggregate


def test_metrics_count_attempts_unique_new_and_results(db):
    db.add(KommoUser(id=1, name="Operator", is_active=True))
    db.add(ContactSnapshot(kommo_contact_id=10, kommo_created_at=datetime(2026, 7, 2, tzinfo=UTC)))
    db.add_all([
        CallEvent(source_type="task", source_id="1", responsible_user_id=1, event_at=datetime(2026,7,2,10,tzinfo=UTC), entity_type="contact", entity_id=10, contact_id=10, target_key="contact:10", result_category="success"),
        CallEvent(source_type="task", source_id="2", responsible_user_id=1, event_at=datetime(2026,7,2,11,tzinfo=UTC), entity_type="contact", entity_id=10, contact_id=10, target_key="contact:10", result_category="failure"),
        CallEvent(source_type="task", source_id="3", responsible_user_id=1, event_at=datetime(2026,7,2,12,tzinfo=UTC), entity_type="lead", entity_id=20, target_key="lead:20", result_category="in_progress"),
    ])
    db.commit()
    p = Period(datetime(2026,7,2,tzinfo=UTC), datetime(2026,7,3,tzinfo=UTC), "", "", "")
    result = aggregate(db, [1], p)
    assert result["total_attempts"] == 3
    assert result["unique_contacts"] == 2
    assert result["new_contacts"] == 1
    assert result["repeat_attempts"] == 1
    assert result["success"] == 1
    assert result["failure"] == 1
    assert result["in_progress"] == 1
    assert result["success_rate"] == 50.0
