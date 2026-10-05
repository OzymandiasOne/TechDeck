"""The Puppet Master's invitation types itself out under a dimmed app
(techdeck/ui/widgets/console_intro.py)."""
import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from techdeck.ui.widgets.console import ConsoleWidget
from techdeck.ui.widgets.console_intro import (
    CARET, Spotlight, markup_prefix, visible_length)

LINK_RE = ConsoleWidget._LINK_MARKUP
MARKUP = "ab [[link|techdeck://x]] cd"


@pytest.fixture
def live_console(qapp, monkeypatch):
    monkeypatch.setattr(ConsoleWidget, "_professional_mode",
                        staticmethod(lambda: False))
    monkeypatch.setattr(ConsoleWidget, "_puppet_master_live",
                        staticmethod(lambda: True))
    host = QWidget()
    host.resize(800, 600)
    layout = QVBoxLayout(host)
    layout.addStretch(1)
    console = ConsoleWidget()
    layout.addWidget(console)
    host.show()
    yield host, console
    host.close()


def _drain(intro):
    """Run the typer to the end without waiting on real timers."""
    intro._typer.stop()
    guard = 0
    while intro.is_running():
        intro._type_next()
        intro._typer.stop()
        guard += 1
        assert guard < 1000


def test_markup_prefix_counts_visible_characters():
    assert visible_length(MARKUP, LINK_RE) == len("ab link cd")
    assert markup_prefix(MARKUP, 0, LINK_RE) == ""
    assert markup_prefix(MARKUP, 2, LINK_RE) == "ab"
    assert markup_prefix(MARKUP, 3, LINK_RE) == "ab "


def test_partly_typed_link_is_already_a_link():
    assert markup_prefix(MARKUP, 5, LINK_RE) == "ab [[li|techdeck://x]]"
    assert markup_prefix(MARKUP, 7, LINK_RE) == "ab [[link|techdeck://x]]"
    assert markup_prefix(MARKUP, 99, LINK_RE) == MARKUP


def test_console_without_an_intro_still_has_the_whole_line(live_console):
    _host, console = live_console
    assert "those limits" in console.output.toPlainText()
    assert "techdeck://cat/summon" in console.output.toHtml()


def test_intro_blanks_the_line_then_types_it_back(live_console):
    host, console = live_console
    assert console.play_greeting_intro(host) is True
    intro = console._greeting_intro
    assert "Your effort" not in console.output.toPlainText()
    assert intro._spotlight is not None

    intro._typer.stop()
    for _ in range(4):
        intro._type_next()
        intro._typer.stop()
    assert console.output.toPlainText().startswith("Your" + CARET)

    _drain(intro)
    text = console.output.toPlainText()
    assert "I can help redefine those limits" in text
    assert CARET not in text
    assert "techdeck://cat/summon" in console.output.toHtml()
    # the summon route's retire-the-line needle still finds it
    assert console.remove_history_line("I can help redefine those limits")


def test_redefine_is_phosphor_green_before_during_and_after(live_console):
    from techdeck.ui.widgets.console_cat import PHOSPHOR
    assert ConsoleWidget.GREETING_LINK_COLOR == PHOSPHOR["bright"]
    green = ConsoleWidget.GREETING_LINK_COLOR.lower()
    host, console = live_console
    assert green in console.output.toHtml().lower()      # authored whole
    console.play_greeting_intro(host)
    intro = console._greeting_intro
    assert green not in console.output.toHtml().lower()  # blanked
    intro._typer.stop()
    while intro._shown < len("Your effort to remain what you are is what "
                             "limits you. I can help red"):
        intro._type_next()
        intro._typer.stop()
    assert green in console.output.toHtml().lower()      # mid-word
    _drain(intro)
    assert green in console.output.toHtml().lower()


def test_other_markup_links_keep_the_body_colour(qapp):
    c = ConsoleWidget()
    assert "#4fd468" not in c.markup_to_html(
        "a [[b|techdeck://x]]", "#FFFFFF").lower()


def test_intro_only_plays_once(live_console):
    host, console = live_console
    assert console.play_greeting_intro(host) is True
    assert console.play_greeting_intro(host) is False


def test_plain_greeting_gets_no_intro(qapp, monkeypatch):
    monkeypatch.setattr(ConsoleWidget, "_puppet_master_live",
                        staticmethod(lambda: False))
    console = ConsoleWidget()
    assert console.play_greeting_intro(None) is False
    assert "TechDeck online" in console.output.toPlainText()


def test_any_keypress_lands_the_whole_line(live_console):
    host, console = live_console
    console.play_greeting_intro(host)
    intro = console._greeting_intro
    QApplication.sendEvent(console.input_field, QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier,
        "a"))
    assert not intro.is_running()
    assert "those limits" in console.output.toPlainText()
    assert console.input_field.text() == "a"    # the key still did its job


def test_clear_mid_type_does_not_overwrite_the_cleared_line(
        live_console, monkeypatch):
    host, console = live_console
    from techdeck.core import audio_manager
    monkeypatch.setattr(audio_manager.get_audio_manager(), "play",
                        lambda *a, **k: None)
    console.play_greeting_intro(host)
    intro = console._greeting_intro
    intro._typer.stop()
    intro._type_next()
    intro._typer.stop()
    console.clear()
    assert not intro.is_running()
    intro._type_next()      # a stray late tick must be harmless
    text = console.output.toPlainText()
    assert "Console cleared." in text
    assert "Your" not in text


def test_spotlight_leaves_a_hole_over_the_console(live_console):
    host, console = live_console
    spot = Spotlight(host, console)
    hole = spot.hole()
    assert hole.height() == console.height()
    assert hole.top() > 0                       # console sits at the bottom
    assert spot.geometry() == host.rect()
    assert spot.testAttribute(
        Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_dim_lifts_after_the_last_character(live_console):
    host, console = live_console
    console.play_greeting_intro(host)
    intro = console._greeting_intro
    _drain(intro)
    assert intro._fader.isActive()
    guard = 0
    while intro._spotlight is not None:
        intro._fade_step()
        guard += 1
        assert guard < 1000
    assert not intro._fader.isActive()
