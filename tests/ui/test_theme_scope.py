"""Scoped themes: one page wearing different colours from the rest of the app.

Reported 2026-10-09 -- the Halloween theme is a pumpkin, and the Assistant is
the page people read dense text on all day. The rules that hold this up:

* a scope override moves ONLY the widgets in that scope,
* the application stylesheet is untouched (the page sets the scoped sheet on
  itself), and
* a scope pinned to a theme that no longer exists follows the app rather than
  falling somewhere the user never chose.
"""

import pytest

from techdeck.ui.theme_aware import ThemeAware
from techdeck.ui.theme_manager import (
    SCOPE_ASSISTANT, ThemeManager, get_theme_manager,
)


@pytest.fixture
def manager():
    """The manager is a singleton, so hand it back the way it was found."""
    tm = get_theme_manager()
    before_theme = tm.get_current_theme()
    before_scope = tm.scope_theme(SCOPE_ASSISTANT)
    yield tm
    tm.set_theme(before_theme)
    tm.set_scope_theme(SCOPE_ASSISTANT, before_scope)


class _Scoped(ThemeAware):
    THEME_SCOPE = SCOPE_ASSISTANT

    def __init__(self):
        self.paints = 0

    def apply_theme(self):
        self.paints += 1


class _Unscoped(ThemeAware):
    def __init__(self):
        self.paints = 0

    def apply_theme(self):
        self.paints += 1


def test_the_manager_is_a_singleton():
    assert ThemeManager() is get_theme_manager()


def test_no_override_means_follow_the_app(manager):
    manager.set_theme("dark")
    manager.set_scope_theme(SCOPE_ASSISTANT, "")
    assert manager.scope_theme(SCOPE_ASSISTANT) == ""
    assert manager.effective_theme(SCOPE_ASSISTANT) == "dark"
    assert manager.palette_for_scope(SCOPE_ASSISTANT) is \
        manager.get_current_palette()
    # Nothing to set on the page: the application sheet already covers it.
    assert manager.scope_stylesheet(SCOPE_ASSISTANT) == ""


def test_an_override_changes_only_that_scope(manager):
    manager.set_theme("dark")
    manager.set_scope_theme(SCOPE_ASSISTANT, "light")
    assert manager.effective_theme(SCOPE_ASSISTANT) == "light"
    assert manager.effective_theme("") == "dark"
    assert manager.palette_for_scope(SCOPE_ASSISTANT) is not \
        manager.get_current_palette()
    assert manager.scope_stylesheet(SCOPE_ASSISTANT)


def test_an_unknown_theme_clears_the_scope_rather_than_guessing(manager):
    """A custom theme that has since been deleted must leave the page
    following the app, not drag it somewhere nobody chose."""
    manager.set_scope_theme(SCOPE_ASSISTANT, "light")
    manager.set_scope_theme(SCOPE_ASSISTANT, "a_theme_that_went_away")
    assert manager.scope_theme(SCOPE_ASSISTANT) == ""


def test_a_scoped_widget_repaints_when_its_scope_moves(manager, qapp):
    manager.set_scope_theme(SCOPE_ASSISTANT, "")
    scoped, plain = _Scoped(), _Unscoped()
    scoped.setup_theme_awareness()
    plain.setup_theme_awareness()
    scoped.paints = plain.paints = 0

    manager.set_scope_theme(SCOPE_ASSISTANT, "light")
    assert scoped.paints == 1
    # The rest of the app must not flicker because one page was re-themed.
    assert plain.paints == 0


def test_every_widget_repaints_when_the_app_theme_moves(manager, qapp):
    manager.set_theme("dark")
    scoped, plain = _Scoped(), _Unscoped()
    scoped.setup_theme_awareness()
    plain.setup_theme_awareness()
    scoped.paints = plain.paints = 0

    manager.set_theme("light")
    assert scoped.paints == 1 and plain.paints == 1


def test_a_scoped_widget_reads_its_own_palette(manager, qapp):
    manager.set_theme("dark")
    manager.set_scope_theme(SCOPE_ASSISTANT, "light")
    scoped, plain = _Scoped(), _Unscoped()
    assert scoped.get_current_palette() is not plain.get_current_palette()
    assert scoped.get_effective_theme_name() == "light"
    assert plain.get_effective_theme_name() == "dark"


def test_an_unknown_scope_name_is_ignored(manager):
    manager.set_scope_theme("", "light")
    assert manager.scope_theme("") == ""


def test_the_assistant_page_carries_the_scoped_sheet(manager, qapp, tmp_path):
    """The page must set the sheet on ITSELF: the application stylesheet still
    comes from the app theme, so nothing else would apply it."""
    from techdeck.core.settings import SettingsManager
    from techdeck.ui.pages.assistant_page import AssistantPage

    manager.set_theme("dark")
    manager.set_scope_theme(SCOPE_ASSISTANT, "")
    page = AssistantPage(SettingsManager(tmp_path / "settings.json"))
    assert page.styleSheet() == ""

    manager.set_scope_theme(SCOPE_ASSISTANT, "light")
    assert "QWidget" in page.styleSheet()

    manager.set_scope_theme(SCOPE_ASSISTANT, "")
    assert page.styleSheet() == ""
