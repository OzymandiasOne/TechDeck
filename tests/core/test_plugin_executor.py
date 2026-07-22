"""Tests for the pure run-outcome logic on PluginExecutor (the 'structured run
outcomes' feature) and PluginResult defaults."""

from techdeck.core.plugin_executor import PluginExecutor, PluginResult, PluginStatus


def test_ticket_units_clamped_to_1_20():
    f = PluginExecutor._ticket_units_from
    assert f({}) == 1
    assert f({"ticket_units": 5}) == 5
    assert f({"ticket_units": 0}) == 1        # never zeroes out
    assert f({"ticket_units": 999}) == 20     # never inflates absurdly
    assert f({"ticket_units": "junk"}) == 1
    assert f({"ticket_units": None}) == 1


def test_run_outcome_honors_only_warning_and_partial():
    f = PluginExecutor._run_outcome_from
    assert f({}) == (None, "")
    assert f({"run_outcome": "nope"}) == (None, "")            # not a dict
    assert f({"run_outcome": {"status": "success"}}) == (None, "")
    assert f({"run_outcome": {"status": "warning", "message": "m"}}) == ("warning", "m")
    assert f({"run_outcome": {"status": "PARTIAL", "message": "x"}}) == ("partial", "x")
    assert f({"run_outcome": {"status": "warning"}}) == ("warning", "")


def test_plugin_result_defaults():
    r = PluginResult(plugin_id="p", status=PluginStatus.SUCCESS, message="ok")
    assert r.ticket_units == 1
    assert r.is_user_error is False
    assert r.user_fix is None
    assert r.outcome_message == ""
    assert r.progress == 0
