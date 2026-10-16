"""ASA: The Video Game - the Woogy message box must hold the simulation.

Headless: these call the real SteelBeamsGame methods against a stub that has
only the attributes they touch, so no Qt window is built.
"""


# ── the Woogy box holds the sim ────────────────────────────────────────────
# Reported 2026-10-15 (Matt Overfield, 0.8.7.8): "Space Probe Stage: Woogy
# introductory text box does not pause action in the background. Player can
# return to 'overrun' game-end screen without an opportunity to respond."
# First contact starts the war and pops the box in the same tick, so the
# armada was killing probes while he read it.

class _Timer:
    def __init__(self, running=True):
        self.running = running

    def isActive(self):
        return self.running

    def stop(self):
        self.running = False

    def start(self):
        self.running = True


class _Box:
    """Stands in for WoogBox: records the on_close hook and can fire it."""

    def __init__(self):
        self.pages = None
        self._on_close = None

    def show_pages(self, pages, on_close=None):
        self.pages = pages
        self._on_close = on_close

    def close_box(self):
        cb, self._on_close = self._on_close, None
        if cb:
            cb()


class _Widget:
    """The attributes _show_woog_dialog / _resume_after_woog touch."""

    def __init__(self, **kw):
        self._timer = _Timer()
        self._woog_box = _Box()
        self.endgame_done = False
        self.game_over = False
        self.positioned = False
        self.__dict__.update(kw)

    def _position_woog_box(self):
        self.positioned = True

    def _resume_after_woog(self):
        # The REAL method, run against this stub — not a reimplementation.
        return _game_cls()._resume_after_woog(self)


def _game_cls():
    from techdeck.ui.widgets.steelbeams_game import SteelBeamsGame
    return SteelBeamsGame


def _show(w, pages=("hello",)):
    _game_cls()._show_woog_dialog(w, pages)


def test_the_woogy_box_stops_the_sim():
    w = _Widget()
    _show(w)
    assert not w._timer.isActive(), "the armada kept firing while he read"


def test_dismissing_the_box_starts_the_sim_again():
    w = _Widget()
    _show(w)
    w._woog_box.close_box()
    assert w._timer.isActive()


def test_the_box_is_wired_to_resume_on_close():
    """Without the on_close hook the sim would stay frozen forever — a worse
    bug than the one being fixed."""
    w = _Widget()
    _show(w)
    assert w._woog_box._on_close is not None


def test_a_lost_game_is_not_restarted_by_the_box_closing():
    """_fire_game_over stops the timer and THEN closes the box, so an
    unguarded resume would set the sim going again under the lose screen."""
    w = _Widget()
    _show(w)
    w.game_over = True
    w._timer.stop()
    w._woog_box.close_box()
    assert not w._timer.isActive()


def test_a_finished_game_is_not_restarted_either():
    w = _Widget()
    _show(w)
    w.endgame_done = True
    w._timer.stop()
    w._woog_box.close_box()
    assert not w._timer.isActive()
