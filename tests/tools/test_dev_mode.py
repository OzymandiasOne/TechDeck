"""Tests for the source-only DevKit gate + session state."""


def test_is_dev_build_true_from_source():
    from techdeck.ui.dev_mode import is_dev_build
    # The test suite runs from source, never frozen.
    assert is_dev_build() is True


def test_frozen_build_is_inert(monkeypatch):
    import techdeck.ui.dev_mode as dm
    monkeypatch.setattr(dm.sys, "frozen", True, raising=False)
    assert dm.is_dev_build() is False
    d = dm.get_dev_mode()
    d.set_active(True)          # must refuse to activate in a frozen build
    assert d.is_active() is False


def test_session_toggle_and_signal(qapp):
    from techdeck.ui.dev_mode import get_dev_mode
    dm = get_dev_mode()
    dm.set_active(False)        # known baseline (singleton persists across tests)

    events = []
    dm.changed.connect(events.append)
    try:
        assert dm.is_active() is False
        dm.set_active(True)
        assert dm.is_active() is True
        dm.set_active(True)     # idempotent — no duplicate signal
        dm.set_active(False)
        assert dm.is_active() is False
        assert events == [True, False]
    finally:
        dm.changed.disconnect(events.append)
        dm.set_active(False)
