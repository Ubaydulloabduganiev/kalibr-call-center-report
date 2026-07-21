from kalibr_amo_bot.sync import _map_result


def test_status_id_wins():
    mapping = {"success_status_ids": [10], "failure_status_ids": [20], "in_progress_status_ids": [30], "success_patterns": [], "failure_patterns": [], "in_progress_patterns": []}
    assert _map_result("", 10, mapping) == "success"


def test_text_patterns():
    mapping = {"success_status_ids": [], "failure_status_ids": [], "in_progress_status_ids": [], "success_patterns": ["успеш"], "failure_patterns": ["отказ"], "in_progress_patterns": ["перезвон"]}
    assert _map_result("Успешный контакт", None, mapping) == "success"
    assert _map_result("Клиент отказался", None, mapping) == "failure"
    assert _map_result("Перезвонить завтра", None, mapping) == "in_progress"
    assert _map_result("", None, mapping) == "no_result"
