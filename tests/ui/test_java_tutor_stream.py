r"""Java Tutor: the three faults behind one bad lesson (2026-09-03).

Reported as: *"it gave me a broken text response. i copy pasted it and told it
this, and then it locked up my scroll wheel halfway up the window."*

1. **Broken text.** The answer contained LaTeX (`$$\frac{n}{2^k} = 1$$`). There is
   no math renderer here, so it reached the screen verbatim.

2. **Locked scroll.** `_rerender` rebuilds the whole document with `setHtml()`.
   Measured on that lesson it cost 110-210ms, against a repaint timer firing
   every 80ms - the repaint never finished before the next began, so the event
   loop never reached the queued wheel events. It freed up when the answer ended,
   which is exactly what he described.

3. **Found while fixing 2:** every message numbered its code blocks from 0, but
   the window keeps ONE list across all of them. The second snippet in a lesson
   rendered as `copy:0`, so clicking Copy on it handed back the FIRST snippet.
   Silent, and wrong in the worst way for an app whose whole job is code.
"""

import sys
import time
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


# --- 1. LaTeX degrades to something readable --------------------------------

@pytest.mark.parametrize("latex, expected", [
    (r"$$n \;/\; 2^k$$", "n / 2^k"),
    (r"$$\frac{n}{2^k} = 1$$", "(n)/(2^k) = 1"),
    (r"$$k = \log_2 n$$", "k = log₂ n"),
    (r"inline $O(\log_2 n)$ here", "inline O(log₂ n) here"),
    (r"$$\frac{a}{b} \le \frac{c}{d}$$", "(a)/(b) ≤ (c)/(d)"),
])
def test_latex_becomes_readable(latex, expected):
    assert render_mod._detex(latex) == expected


def test_log_keeps_its_name():
    r"""Regression: `\b` does not match between "g" and "_" in `\log_2` (both are
    word characters), so the command was stripped as unknown and the output was a
    bare subscript."""
    assert "log" in render_mod._detex(r"$$\log_2 n$$")


def test_ordinary_prose_is_untouched():
    for plain in ("plain text with no math",
                  "a `code span` and **bold**",
                  "costs $5 today"):
        assert render_mod._detex(plain) == plain


def test_no_raw_latex_survives_to_html(win):
    html, _ = win._bubble("assistant", r"So $$\frac{n}{2^k} = 1$$ therefore.",
                          win._pal)
    assert "$$" not in html and "\\frac" not in html


# --- 2. the repaint can never starve the event loop -------------------------

def test_repaint_books_the_next_one_by_what_it_cost(win, monkeypatch):
    """The load-bearing guarantee: whatever a repaint costs, it may not occupy
    more than 1/_STREAM_DUTY of wall time."""
    slow_ms = 150.0

    def slow_rerender():
        time.sleep(slow_ms / 1000.0)

    monkeypatch.setattr(win, "_rerender", slow_rerender)
    win._streaming_live = True
    win._stream_tick()

    booked = win._repaint_timer.remainingTime()
    assert booked >= slow_ms * (tutor._STREAM_DUTY - 1), (
        f"repaint cost ~{slow_ms}ms but only {booked}ms was left for input - "
        f"this is the scroll lock")


def test_a_cheap_repaint_stays_at_the_floor(win, monkeypatch):
    monkeypatch.setattr(win, "_rerender", lambda: None)
    win._streaming_live = True
    win._stream_tick()
    assert win._repaint_timer.remainingTime() <= tutor._STREAM_REPAINT_MS


def test_the_interval_is_capped(win, monkeypatch):
    def very_slow():
        time.sleep(0.5)
    monkeypatch.setattr(win, "_rerender", very_slow)
    win._streaming_live = True
    win._stream_tick()
    assert win._repaint_timer.remainingTime() <= tutor._STREAM_REPAINT_MAX_MS


def test_a_finished_turn_does_not_book_another_repaint(win, monkeypatch):
    monkeypatch.setattr(win, "_rerender", lambda: None)
    win._streaming_live = False
    win._stream_tick()
    assert not win._repaint_timer.isActive()


# --- caching the settled messages -------------------------------------------

def test_settled_messages_are_rendered_once(win, monkeypatch):
    win._messages = [("assistant", "one"), ("user", "two")]
    win._rerender()

    calls = []
    real = win._bubble
    monkeypatch.setattr(win, "_bubble",
                        lambda *a, **k: (calls.append(a[0]), real(*a, **k))[1])
    win._streaming = "a live answer"
    win._rerender()

    assert calls == ["assistant"], (
        f"settled messages were re-rendered: {calls} - only the live tail should be")


def test_switching_lesson_clears_the_cache(win):
    win._messages = [("assistant", "one")]
    win._rerender()
    assert win._bubble_cache
    win._new_lesson()
    assert not win._bubble_cache


# --- 3. Copy links point at their own code ----------------------------------

def test_each_copy_link_returns_its_own_snippet(win):
    import re
    win._messages = [
        ("assistant", "first\n\n```java\nint A = 1;\n```\n"),
        ("assistant", "second\n\n```java\nint B = 2;\n```\n"),
        ("user", "mine\n\n```java\nint C = 3;\n```\n"),
    ]
    win._rerender()

    links = [int(n) for n in re.findall(r"copy:(\d+)", win._view.toHtml())]
    assert links == [0, 1, 2], f"code blocks misnumbered: {links}"
    for index, expected in zip(links, ["int A = 1;", "int B = 2;", "int C = 3;"]):
        assert win._code_blocks[index] == expected


def test_a_single_message_with_two_blocks_numbers_both(win):
    import re
    win._messages = [("assistant",
                      "```java\nint A = 1;\n```\nand\n```java\nint B = 2;\n```\n")]
    win._rerender()
    assert [int(n) for n in re.findall(r"copy:(\d+)", win._view.toHtml())] == [0, 1]
