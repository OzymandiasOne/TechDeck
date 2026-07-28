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


def test_confirm_lock_flickers_and_decays(qapp):
    """A committed click triggers the confirm flicker over the existing lock."""
    from PySide6.QtCore import QRectF as _R
    dlg, overlay = _make_overlay(qapp)
    rect = _R(200, 150, 180, 36)
    overlay.set_lock(rect, "BATCH 504")
    overlay._lock_rect = rect
    assert overlay._confirm_ticks == 0

    overlay.confirm_lock()
    assert overlay._confirm_ticks > 0                 # flicker armed
    assert overlay._lock_solid                        # snapped to solid lock
    assert "CONFIRMED" in overlay._callout

    for _ in range(20):                               # flicker decays to nothing
        overlay._tick()
    assert overlay._confirm_ticks == 0

    overlay._timer.stop()
    overlay.deleteLater()
    dlg.deleteLater()


def test_confirm_lock_noop_without_lock(qapp):
    dlg, overlay = _make_overlay(qapp)
    overlay._lock_rect = None
    overlay.confirm_lock()
    assert overlay._confirm_ticks == 0                # nothing to confirm
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


# ── two-phase (911 Repeater) sequence tests ──────────────────────────────


def test_wipe_holds_dark_then_zoom_reaches_aim(qapp):
    """wipe (mid-callback fires once) → hold → zoom → aim; the dialog is
    never exposed between the wipe and the zoom."""
    from PySide6.QtCore import QRectF as _R
    from PySide6.QtGui import QPixmap
    dlg, overlay = _make_overlay(qapp)
    beats = []
    overlay.begin_wipe(lambda: beats.append("mid"), lambda: beats.append("done"))
    assert overlay._state == "wipe"
    _drive(overlay, 60)                       # ≈1 s: wipe is long over
    assert beats == ["mid", "done"]           # each beat fired exactly once
    assert overlay._state == "hold"           # holds dark until begin_zoom

    overlay.begin_zoom(QPixmap(100, 80), _R(100, 100, 400, 300),
                       lambda: beats.append("zoomed"))
    assert overlay._state == "zoom"
    _drive(overlay, 60)
    assert beats[-1] == "zoomed"
    assert overlay._state == "aim"

    overlay._timer.stop()
    overlay.deleteLater()
    dlg.deleteLater()


def test_salvo_strikes_all_targets_then_done(qapp):
    """fire_salvo: staggered impacts across every point, knockout on the
    last, then the TARGETS NEUTRALIZED AAR and the CRT close."""
    from PySide6.QtCore import QPointF
    dlg, overlay = _make_overlay(qapp)
    pts = [QPointF(200, 150), QPointF(200, 200), QPointF(200, 250)]
    overlay._aar_title = "TARGETS NEUTRALIZED"
    overlay._aar_extra = "3 TARGETS DESTROYED"
    done = []
    overlay.fire_salvo(pts, lambda: done.append(True))
    assert len(overlay._salvo) == 3

    _drive(overlay, 70)                       # flight ends, first strike lands
    assert overlay._state == "burst"
    seen = set()
    for _ in range(800):
        if overlay._state == "done":
            break
        overlay._tick()
        seen.add(overlay._state)
    assert all(s["fired"] for s in overlay._salvo)
    assert "aar" in seen and "crt" in seen
    assert overlay._state == "done"
    assert _wait_for(lambda: done == [True])

    overlay._timer.stop()
    overlay.deleteLater()
    dlg.deleteLater()


def test_salvo_volume_ramps_and_gaps_jitter(qapp):
    """Impact volume climbs 0.6 → 1.0 (capped on the 5th strike) and the
    barrage gaps are irregular but inside the double-tap/normal bounds."""
    from PySide6.QtCore import QPointF
    from techdeck.ui.widgets import chopper_picker as cp
    dlg, overlay = _make_overlay(qapp)
    overlay.fire_salvo([QPointF(0, i * 10) for i in range(7)], lambda: None)

    vols = [s["vol"] for s in overlay._salvo]
    assert vols == [0.6, 0.7, 0.8, 0.9, 1.0, 1.0, 1.0]

    times = [s["at"] for s in overlay._salvo]
    assert times[0] == 0.0
    gaps = [b - a for a, b in zip(times, times[1:])]
    lo = cp._SALVO_DOUBLETAP_MS[0]
    hi = cp._SALVO_GAP_MS[1]
    assert all(lo <= g <= hi for g in gaps), gaps

    overlay.skip()                      # tidy up without playing it out
    _drive(overlay, 60)
    overlay._timer.stop()
    overlay.deleteLater()
    dlg.deleteLater()


def test_salvo_skip_clears_and_closes(qapp):
    """Any-key skip mid-salvo drops the remaining strikes and still closes."""
    from PySide6.QtCore import QPointF
    dlg, overlay = _make_overlay(qapp)
    done = []
    overlay.fire_salvo([QPointF(100, 100), QPointF(100, 200)],
                       lambda: done.append(True))
    _drive(overlay, 5)
    overlay.skip()
    assert overlay._salvo == []
    assert overlay._state == "crt"
    _drive(overlay, 60)
    assert overlay._state == "done"
    assert _wait_for(lambda: done == [True])

    overlay._timer.stop()
    overlay.deleteLater()
    dlg.deleteLater()


class _TargetConsole:
    """Console with the two-phase request_target_folders method."""

    def __init__(self, result):
        self._result = result
        self.args_seen = None

    def request_target_folders(self, title, start_dir, target_pattern):
        self.args_seen = (title, start_dir, target_pattern)
        return self._result


def test_sdk_nest_targets_ok_passes_through():
    console = _TargetConsole(("ok", "C:/qtdr/V109", ["504100", "504101"]))
    status, path, names = sdk.request_nest_targets(
        {"console": console}, "t", "C:/qtdr", target_pattern=r"\d+")
    assert (status, path, names) == ("ok", "C:/qtdr/V109", ["504100", "504101"])
    assert console.args_seen == ("t", "C:/qtdr", r"\d+")


def test_sdk_nest_targets_unavailable_without_console_method():
    """Old console (no request_target_folders) and headless both report
    unavailable so the plugin falls back to its classic flow."""
    assert sdk.request_nest_targets({"console": _OldConsole()}, "t")[0] == \
        "unavailable"
    assert sdk.request_nest_targets({}, "t")[0] == "unavailable"


def test_sdk_nest_targets_unavailable_on_error():
    class _Boom:
        def request_target_folders(self, *a):
            raise RuntimeError("picker exploded")
    assert sdk.request_nest_targets({"console": _Boom()}, "t")[0] == \
        "unavailable"
