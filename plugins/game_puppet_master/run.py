"""
Puppet Master - his table, as a Library cartridge.

A thin launcher: the game itself ships in the app bundle
(techdeck.ui.void_game, listed in TechDeck.spec hiddenimports). The plugin
is `locked` + `show_locked`, so the Library shows it greyed out until the
table has been opened once another way (asking him, or /play) - that first
opening unlocks it (CommandHandler.discover_table) with the success jingle.
It is also `gate: puppet_master`: while his flag is off the loader never
discovers it at all.
"""


def run(params, progress_callback, cancel_event):
    log = params.get("log", print)
    # GUI plugin: requires_main_thread is set, so this runs on the Qt thread.
    # The window is owned at module level inside void_game.window (open_table),
    # so Qt cannot collect it.
    from techdeck.ui.void_game.window import open_table
    open_table()
    log("The table is set.")
    progress_callback(100)
