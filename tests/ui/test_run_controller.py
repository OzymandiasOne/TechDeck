"""Functional tests for the run orchestration extracted into RunController /
RunSession. Uses a real HomePage (which builds a real RunController) with a
temp settings store."""

from techdeck.core.settings import SettingsManager
from techdeck.core.run_session import RunSession


def _home(tmp_path):
    from techdeck.ui.pages.home_page import HomePage
    return HomePage(SettingsManager(settings_dir=tmp_path))


def test_run_session_defaults():
    s = RunSession()
    assert s.is_running is False
    assert s.queue == [] and s.params == {}
    assert set(s.shared_state) == {"911", "922", "General"}
    assert s.paused is False and s.paused_tile_id is None
    assert s.shelve_after_current is False


def test_controller_wired_to_home(qapp, tmp_path):
    home = _home(tmp_path)
    assert type(home._run).__name__ == "RunController"
    assert isinstance(home._run.session, RunSession)
    assert home._run.is_running is False


def test_button_mode_toggles_is_running(qapp, tmp_path):
    home = _home(tmp_path)
    # No run button wired in a bare HomePage; the methods still flip the flag
    # (they set it before the run_btn guard returns).
    home._run.set_button_cancel_mode()
    assert home._run.is_running is True
    home._run.set_button_run_mode()
    assert home._run.is_running is False


def test_apply_plugin_status_updates_card(qapp, tmp_path):
    home = _home(tmp_path)

    class _Card:
        def __init__(self):
            self.status = None

        def set_status(self, s):
            self.status = s

    card = _Card()
    home.tile_cards["x"] = card
    home._run._apply_plugin_status("x", "running")
    assert card.status == "running"


def test_shelf_save_view_clear_roundtrip(qapp, tmp_path):
    home = _home(tmp_path)
    home._run.session.shared_state = {"911": {}, "922": {"batch_number": "473"},
                                      "General": {}}
    home._run._save_shelf(["plugin_a", "plugin_b"])

    shelf = home.settings.get_shelf()
    assert shelf is not None
    assert shelf["remaining_tile_ids"] == ["plugin_a", "plugin_b"]
    assert shelf["shared_state"]["922"]["batch_number"] == "473"

    home.view_shelf()                         # must not raise (no console -> silent)
    home.clear_shelf()
    assert home.settings.get_shelf() is None


def test_drain_log_buffer_all_emits(qapp, tmp_path):
    home = _home(tmp_path)
    seen = []
    home.plugin_log.connect(lambda tid, msg: seen.append((tid, msg)))
    home._run._log_buffer.put(("tid", "hello"))
    home._drain_log_buffer_all()              # delegates to controller
    assert ("tid", "hello") in seen


def test_pause_with_nothing_running_is_safe(qapp, tmp_path):
    home = _home(tmp_path)
    # is_running False -> "Nothing to pause"; must not raise or change state.
    home.pause_run()
    assert home._run.is_running is False
