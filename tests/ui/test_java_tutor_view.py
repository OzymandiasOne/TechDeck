"""Java Tutor transcript: it stays a dark code surface, and it holds your scroll.

Two reported problems, 2026-09-02:

1. "when I paste a response, I'm stuck at the top of the scroll and can't scroll
   down for a few seconds." `setHtml()` rebuilds the document and resets the
   scrollbar to 0. That runs every _STREAM_REPAINT_MS while an answer streams, so
   unless the position is saved and put back, the view yanks you to the top a
   dozen times a second for as long as the answer takes.

2. "hard to tell where your text and my text end or begin." The tutor's replies
   were a bare div with no label; and `_palette` used to overwrite the One Dark
   syntax colours with the active app theme, so a light theme made a light chat
   area with colours picked for a dark one.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.devkit.java_tutor import render as render_mod  # noqa: E402
from tools.devkit.java_tutor import run as tutor  # noqa: E402


@pytest.fixture
def win(qapp, monkeypatch):
    monkeypatch.setattr(tutor.claude_session, "find_claude", lambda: "claude.exe")
    return tutor.JavaTutorWindow()


# --- the transcript stays a code surface ------------------------------------

class _LightPalette:
    """A light theme, the case that used to break the transcript."""
    text = "#111111"
    text_secondary = "#555555"
    console_bg = "#ffffff"
    border = "#dddddd"
    accent = "#0044cc"
    font_family = '"Comic Sans MS"'


def test_a_light_theme_does_not_repaint_the_transcript(monkeypatch):
    monkeypatch.setattr(tutor, "get_theme_manager",
                        lambda: type("M", (), {"get_current_palette":
                                               staticmethod(lambda: _LightPalette())})())
    pal = tutor._palette()
    assert pal["chat_bg"] == render_mod.DEFAULTS["chat_bg"]
    assert pal["text"] == render_mod.DEFAULTS["text"]        # NOT #111111
    assert pal["code_bg"] == render_mod.DEFAULTS["code_bg"]  # NOT #ffffff
    assert pal["accent"] == render_mod.DEFAULTS["accent"]


def test_the_theme_font_is_still_honoured(monkeypatch):
    """Some themes pick a monospace face deliberately; that is a look, not a bug."""
    monkeypatch.setattr(tutor, "get_theme_manager",
                        lambda: type("M", (), {"get_current_palette":
                                               staticmethod(lambda: _LightPalette())})())
    assert tutor._palette()["font_family"] == '"Comic Sans MS"'


def test_a_broken_theme_manager_falls_back_instead_of_raising(monkeypatch):
    def boom():
        raise RuntimeError("no theme")
    monkeypatch.setattr(tutor, "get_theme_manager",
                        lambda: type("M", (), {"get_current_palette":
                                               staticmethod(boom)})())
    assert tutor._palette()["chat_bg"] == render_mod.DEFAULTS["chat_bg"]


def test_the_widget_itself_is_painted_black(win):
    """Not just the body HTML - the stylesheet, or the theme's panel colour
    shows through the document margin and behind the scrollbar."""
    sheet = win._view.styleSheet()
    assert win._pal["chat_bg"] in sheet
    assert win._pal["chat_bg"] in win._input.styleSheet()


# --- telling the two speakers apart -----------------------------------------

def test_both_speakers_are_named(win):
    assert ">You<" in win._bubble("user", "q", win._pal)[0]
    assert ">Java Tutor<" in win._bubble("assistant", "a", win._pal)[0]


def test_the_two_speakers_use_different_colours(win):
    pal = win._pal
    assert pal["user"] != pal["tutor"]
    assert pal["user"] in win._bubble("user", "q", pal)[0]
    assert pal["tutor"] in win._bubble("assistant", "a", pal)[0]
    # and neither borrows the other's colour
    assert pal["tutor"] not in win._bubble("user", "q", pal)[0]


def test_errors_stay_visually_separate(win):
    html, _ = win._bubble("error", "it broke", win._pal)
    assert "#ff8b8b" in html
    assert ">You<" not in html and ">Java Tutor<" not in html


# --- scrolling ---------------------------------------------------------------

def _fill(qapp, win, n=60):
    """Enough messages to scroll, and actually laid out.

    A widget that has never been shown reports maximum() == 0 even offscreen, so
    the scroll tests would silently skip - and these two ARE the reported bug.
    """
    win._messages = [("user" if i % 2 == 0 else "assistant",
                      f"message {i} " + ("filler text " * 12)) for i in range(n)]
    win._view.setFixedHeight(200)
    win.show()
    qapp.processEvents()
    win._rerender()
    qapp.processEvents()


def test_scroll_position_survives_a_rerender(qapp, win):
    _fill(qapp, win)
    bar = win._view.verticalScrollBar()
    assert bar.maximum() > 0, "document should be scrollable - the test is meaningless otherwise"

    middle = bar.maximum() // 2
    bar.setValue(middle)
    assert not win._is_at_bottom()

    win._rerender()          # what the stream timer does, repeatedly

    assert bar.value() == middle, (
        "the transcript jumped away from where the reader left it - this is the "
        "'stuck at the top' bug")


def test_still_follows_the_answer_when_parked_at_the_bottom(qapp, win):
    _fill(qapp, win)
    bar = win._view.verticalScrollBar()
    assert bar.maximum() > 0, "document should be scrollable - the test is meaningless otherwise"

    win._scroll_to_bottom()
    assert win._is_at_bottom()

    win._messages.append(("assistant", "a new answer " + ("more text " * 40)))
    win._rerender()

    assert win._is_at_bottom(), "reading at the bottom should keep following along"


# --- his messages sit on a filled panel ------------------------------------

def _painted(qapp, win, messages, size=(600, 400)):
    """What colours the transcript ACTUALLY paints.

    Asserting the colour is in the HTML proves nothing - Qt rich text supports
    only a subset of CSS and silently drops the rest. So render to an image and
    count pixels.
    """
    from collections import Counter
    from PySide6.QtGui import QImage

    win._messages = list(messages)
    win._view.setFixedSize(*size)
    win.show()
    qapp.processEvents()
    win._rerender()
    qapp.processEvents()

    img = QImage(size[0], size[1], QImage.Format.Format_RGB32)
    win._view.render(img)
    return Counter(QImage.pixelColor(img, x, y).name()
                   for y in range(0, size[1], 2) for x in range(0, size[0], 4))


def test_your_messages_get_a_panel_and_the_tutor_does_not(qapp, win):
    pal = win._pal
    counts = _painted(qapp, win, [("user", "my question here"),
                                  ("assistant", "my answer here " * 6)])
    assert counts.get(pal["user_bg"], 0) > 0, (
        "your message has no panel behind it - Qt dropped the background-color")
    assert counts.get(pal["chat_bg"], 0) > counts.get(pal["user_bg"], 0), (
        "the tutor's side should stay on the bare black; the alternation is the "
        "whole point")


def test_a_code_block_inside_your_message_still_reads_as_a_block(qapp, win):
    """Three steps, darkest to lightest: chat < your panel < code. If code_bg sits
    too close to user_bg, pasted Java disappears into the panel."""
    pal = win._pal
    message = "\n".join([
        "here is my code",
        "",
        "```java",
        "public int sum(int n) {",
        "    return n;",
        "}",
        "```",
        "",
        "is it right?",
    ])
    counts = _painted(qapp, win, [("user", message)])
    for key in ("chat_bg", "user_bg", "code_bg"):
        assert counts.get(pal[key], 0) > 0, f"{key} ({pal[key]}) never painted"
    assert len({pal["chat_bg"], pal["user_bg"], pal["code_bg"]}) == 3


def test_the_tutor_bubble_carries_no_panel_colour(win):
    assert win._pal["user_bg"] not in win._bubble("assistant", "a", win._pal)[0]
    assert win._pal["user_bg"] in win._bubble("user", "q", win._pal)[0]
