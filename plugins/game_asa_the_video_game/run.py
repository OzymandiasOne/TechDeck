"""
Steel Tube Op — GUI game plugin.

Launches the Steel Tube Operation arcade mini-game. It's a "Games"-family,
purchasable plugin: the Library hides it until it's unlocked at Woogy's
Emporium (gated on settings.is_unlocked("game_asa_the_video_game")). The game widget
itself ships in the app bundle (techdeck.ui.widgets.steelbeams_game).
"""

_window = None  # module-level so Qt doesn't garbage-collect the window


def run(params, progress_callback, cancel_event):
    global _window
    log = params.get('log', print)
    # GUI plugin: requires_main_thread is set, so this runs on the Qt thread.
    from techdeck.ui.widgets.steelbeams_game import SteelBeamsGame
    if _window is not None:
        try:
            if _window.isVisible():
                _window.raise_()
                _window.activateWindow()
                progress_callback(100)
                return
        except RuntimeError:
            _window = None
    _window = SteelBeamsGame()
    _window.show()
    _window.raise_()
    _window.activateWindow()
    log("Steel Tube Operation launched — have fun!")
    progress_callback(100)
