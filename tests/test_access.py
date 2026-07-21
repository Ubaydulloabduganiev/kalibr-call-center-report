from kalibr_amo_bot.access import scoped_user_ids
from kalibr_amo_bot.models import AccessPolicy, KommoUser


def test_operator_scope(db):
    user = KommoUser(id=1, name="A", is_active=True, group_id=7)
    db.add_all([user, KommoUser(id=2, name="B", is_active=True, group_id=7)])
    db.commit()
    policy = AccessPolicy(kommo_user_id=1, enabled=True, access_level="operator")
    assert scoped_user_ids(db, user, policy) == [1]


def test_manager_group_scope(db):
    user = KommoUser(id=1, name="A", is_active=True, group_id=7)
    db.add_all([user, KommoUser(id=2, name="B", is_active=True, group_id=7), KommoUser(id=3, name="C", is_active=True, group_id=8)])
    db.commit()
    policy = AccessPolicy(kommo_user_id=1, enabled=True, access_level="manager")
    assert set(scoped_user_ids(db, user, policy)) == {1, 2}
