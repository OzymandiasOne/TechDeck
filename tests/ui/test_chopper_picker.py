"""Chopper-gunner picker (chopper_picker.py) — offscreen sequence + SDK
version-tolerance tests. The interactive dialog itself needs a live screen;
these cover the FX state machine end-to-end and the wiring contracts."""

from PySide6.QtCore import QRect, QRectF

from techdeck.core import plugin_sdk as sdk


def _make_overlay(qapp):
    from PySide6.QtWidgets import QDialog
    from techdeck.ui.widgets.chopper_picker import GunnerOverlay

    dlg = QDialog()
    dlg.resize(400, 300)
    overlay = GunnerOverlay(dlg, QRect(0, 0, 800, 600))
    return dlg, overlay


def _drive(overlay, ticks):
    for _ in range(ticks):
        if overlay._state == "done":
            break
        overlay._tick()


def _wait_for(pred, timeout_ms=2000):
    """Pump the event loop until pred() is true or timeout — deterministic
    regardless of test ordering (a fixed qWait can miss the singleShot under
    full-suite load on the offscreen platform)."""
    from PySide6.QtCore import QDeadlineTimer
    from PySide6.QtWidgets import QApplication
    deadline = QDeadlineTimer(timeout_ms)
    while not pred() and not deadline.hasExpired():
        QApplication.processEvents()
    return pred()


def test_fire_sequence_runs_to_done(qapp):
    """flight → burst (particles + glitch together) → AAR → CRT close → done."""
    dlg, overlay = _make_overlay(qapp)
    overlay._impact = QRectF(0, 0, 800, 600).center()
    done = []
    overlay.fire(lambda: done.append(True))

    _drive(overlay, 70)                      # ≈1.1 s: flight ends, burst begins
    assert overlay._state == "burst"
    assert len(overlay._parts) > 500         # the 840-fragment burst spawned
    assert overlay._puffs                    # dust haze spawned
    assert overlay._knock_ticks > 0          # glitch fires WITH the impact

    # Burst settles → TARGET NEUTRALIZED after-action hold → CRT collapse.
    seen = set()
    for _ in range(600):
        if overlay._state == "done":
            break
        overlay._tick()
        seen.add(overlay._state)
    assert "aar" in seen                     # after-action screen shown
    assert "crt" in seen                     # CRT power-off phase ran
    assert overlay._state == "done"
    assert _wait_for(lambda: done == [True])  # cb delivered when CRT ends

    overlay._timer.stop()
    overlay.deleteLater()
    dlg.deleteLater()


def test_skip_then_crt_close(qapp):
    """Any-key skip clears FX and still plays the CRT close before finishing."""
    dlg, overlay = _make_overlay(qapp)
    overlay._impact = QRectF(0, 0, 800, 600).center()
    done = []
    overlay.fire(lambda: done.append(True))
    _drive(overlay, 5)
    overlay.skip()
    assert not overlay._parts and not overlay._smoke and not overlay._puffs
    assert overlay._state == "crt"           # skip goes straight to the CRT close
    _drive(overlay, 60)                      # let the CRT collapse finish
    assert overlay._state == "done"
    assert _wait_for(lambda: done == [True])

    overlay._timer.stop()
    overlay.deleteLater()
    dlg.deleteLater()


class _OldConsole:
    """A console predating the style parameter."""

    def request_directory(self, title, start_dir):
        return "C:/old-console-path"


class _NewConsole:
    def __init__(self):
        self.style_seen = "unset"

    def request_directory(self, title, start_dir, style=None):
        self.style_seen = style
        return "C:/new-console-path"


def test_sdk_style_falls_back_on_old_console():
    """A new plugin drop on an old TechDeck (no style kwarg) still works."""
    result = sdk.request_directory({"console": _OldConsole()}, "t", "",
                                   style="chopper_gunner")
    assert result == "C:/old-console-path"


def test_sdk_style_passes_through():
    console = _NewConsole()
    result = sdk.request_directory({"console": console}, "t", "",
                                   style="chopper_gunner")
    assert result == "C:/new-console-path"
    assert console.style_seen == "chopper_gunner"


def test_sdk_no_style_uses_two_arg_call():
    console = _NewConsole()
    result = sdk.request_directory({"console": console}, "t", "")
    assert result == "C:/new-console-path"
    assert console.style_seen is None
