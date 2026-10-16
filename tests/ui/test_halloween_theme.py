"""The halloween theme — registered, dark-iconed, seasonally stocked."""

from techdeck.ui.theme import THEMES, generate_stylesheet, is_builtin_theme


def test_halloween_theme_is_registered_and_builtin():
    assert "halloween" in THEMES
    assert is_builtin_theme("halloween")
    assert THEMES["halloween"].background == "#1E0F2E"  # purple body
    assert THEMES["halloween"].card_text == "#2A1503"    # dark tile names
    assert THEMES["halloween"].splitter_handle == "#4A1F7A"  # purple resize edge
    assert THEMES["halloween"].surface == "#FF7A1A"      # tiles wear THE orange
    assert THEMES["halloween"].accent == "#4A1F7A"       # witching-purple buttons
    assert THEMES["halloween"].console_bg == "#12081C"   # dark-purple console
    assert THEMES["halloween"].sidebar_bg == "#1E0F2E"   # dark-purple ribbon
    css = generate_stylesheet("halloween")
    assert "#FF7A1A" in css


def test_halloween_counts_as_a_light_theme_for_icons():
    # Bright pumpkin background -> dark icon set, like the light themes.
    from techdeck.ui.widgets.sidebar import _icon_folder_for_theme
    assert _icon_folder_for_theme("halloween") == "dark"


# The picker's seasonal stock is pinned in test_theme_picker_stock.py, which
# calls SettingsPage._theme_choices itself. A test that lived here used to
# assert halloween_active() instead and passed happily while the picker was a
# one-way door for professional users (2026-10-16) — testing the gate the code
# HAPPENED to call, not the behaviour, proves nothing.
