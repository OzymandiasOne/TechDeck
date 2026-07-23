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
    """flight → burst (particles spawn) → knockout → done, dialog restored."""
    dlg, overlay = _make_overlay(qapp)
    overlay._impact = QRectF(0, 0, 800, 600).center()
    done = []
    overlay.fire(lambda: done.append(True))

    _drive(overlay, 70)                      # ≈1.1 s: flight ends, burst begins
    assert overlay._state in ("burst", "knockout")
    assert len(overlay._parts) > 500         # the 840-fragment burst spawned
    assert overlay._puffs                    # dust haze spawned

    _drive(overlay, 400)                     # burst + knockout play out
    assert overlay._state == "done"
    assert dlg.windowOpacity() == 1.0        # knockout flicker restored

    assert _wait_for(lambda: done == [True])  # _finish delivers cb after 250 ms

    overlay._timer.stop()
    overlay.deleteLater()
    dlg.deleteLater()


def test_skip_jumps_to_done(qapp):
    """Any-key skip mid-flight: immediate completion, no stranded FX."""
    dlg, overlay = _make_overlay(qapp)
    overlay._impact = QRectF(0, 0, 800, 600).center()
    done = []
    overlay.fire(lambda: done.append(True))
    _drive(overlay, 5)
    overlay.skip()
    assert overlay._state == "done"
    assert not overlay._parts and not overlay._smoke and not overlay._puffs
    assert dlg.windowOpacity() == 1.0

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
