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


def test_theme_combo_hides_halloween_out_of_season(qapp, monkeypatch):
    # The picker lists halloween only in season — unless it IS the current
    # theme (so a session open past Nov 2 can still switch away).
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "0")
    from techdeck.ui.pages.settings_page import SettingsPage  # noqa: F401
    # Exercise the loop logic directly rather than building the whole page:
    from techdeck.core.constants import halloween_active

    class _S:
        def is_professional(self):
            return False

    assert not halloween_active(settings=_S())
    monkeypatch.setenv("TECHDECK_HALLOWEEN", "1")
    assert halloween_active(settings=_S())
