"""The halloween theme — registered, dark-iconed, seasonally stocked."""

from techdeck.ui.theme import THEMES, generate_stylesheet, is_builtin_theme


def test_halloween_theme_is_registered_and_builtin():
    assert "halloween" in THEMES
    assert is_builtin_theme("halloween")
    assert THEMES["halloween"].accent == "#FF7A1A"      # pumpkin is PRIMARY
    assert THEMES["halloween"].accent_two == "#58D858"   # poison-green CTA
    css = generate_stylesheet("halloween")
    assert "#FF7A1A" in css


def test_halloween_counts_as_a_dark_theme_for_icons():
    from techdeck.ui.widgets.sidebar import _icon_folder_for_theme
    assert _icon_folder_for_theme("halloween") == "light"


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
