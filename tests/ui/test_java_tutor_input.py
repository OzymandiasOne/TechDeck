"""Java Tutor message box: Enter sends, Shift+Enter is a newline, Esc takes it back.

The send key had to move from Ctrl+Enter to Enter, which means the box must see
Return BEFORE QTextEdit turns it into a newline - a QShortcut is too late, hence
the InputBox subclass.

Esc is the interesting one. `interrupt()` does not return synchronously: it kills
the process, and the turn still arrives at `turn_finished` carrying whatever
partial answer streamed in. So the undo cannot happen in the Esc handler; the
intent is carried on `_cancelling` and spent in the finish handler. These tests
pin that, because getting it wrong leaves a half-answer in the transcript and the
user's message gone.
"""

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QTextCursor

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.devkit.java_tutor import run as tutor  # noqa: E402


def _key(box, key, mods=Qt.KeyboardModifier.NoModifier, text="\r"):
    box.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key, mods, text))


@pytest.fixture
def box(qapp):
    return tutor.InputBox()


# --- the send key -----------------------------------------------------------

def test_enter_sends_and_does_not_insert_a_newline(box):
    fired = []
    box.send_requested.connect(lambda: fired.append(True))
    box.setPlainText("what is O(n)")
    _key(box, Qt.Key.Key_Return)
    assert fired == [True]
    assert box.toPlainText() == "what is O(n)"      # no stray newline


def test_shift_enter_inserts_a_newline_and_does_not_send(box):
    fired = []
    box.send_requested.connect(lambda: fired.append(True))
    box.setPlainText("line one")
    box.moveCursor(QTextCursor.MoveOperation.End)   # setPlainText parks it at 0
    _key(box, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert fired == []
    assert box.toPlainText() == "line one\n"


def test_ctrl_enter_still_sends(box):
    """It was the only way to send for months; the muscle memory is real."""
    fired = []
    box.send_requested.connect(lambda: fired.append(True))
    _key(box, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert fired == [True]


def test_keypad_enter_sends_too(box):
    fired = []
    box.send_requested.connect(lambda: fired.append(True))
    _key(box, Qt.Key.Key_Enter)
    assert fired == [True]


def test_ordinary_typing_is_untouched(box):
    fired = []
    box.send_requested.connect(lambda: fired.append(True))
    box.cancel_requested.connect(lambda: fired.append("cancel"))
    _key(box, Qt.Key.Key_A, text="a")
    assert fired == []
    assert box.toPlainText() == "a"


def test_escape_asks_to_cancel(box):
    fired = []
    box.cancel_requested.connect(lambda: fired.append(True))
    _key(box, Qt.Key.Key_Escape, text="")
    assert fired == [True]


# --- cancel / undo ----------------------------------------------------------

class _FakeSession:
    """Stands in for ClaudeSession: just busy-ness and an interrupt count."""

    def __init__(self, busy=False):
        self.busy = busy
        self.interrupts = 0

    def interrupt(self):
        self.interrupts += 1


@pytest.fixture
def win(qapp, monkeypatch):
    """A tutor window with the engine stubbed out - no Claude process is run."""
    monkeypatch.setattr(tutor.claude_session, "find_claude", lambda: "claude.exe")
    w = tutor.JavaTutorWindow()
    w._session = _FakeSession()
    return w


def test_escape_is_silent_when_nothing_is_in_flight(win):
    """Esc must never be a way to lose what you have typed."""
    win._input.setPlainText("half-written question")
    win._cancel_send()
    assert win._session.interrupts == 0
    assert win._cancelling is False
    assert win._input.toPlainText() == "half-written question"


def test_escape_during_a_turn_interrupts_and_arms_the_undo(win):
    win._session.busy = True
    win._cancel_send()
    assert win._session.interrupts == 1
    assert win._cancelling is True


def test_undo_pops_the_user_message_and_hands_the_text_back(win):
    win._messages = [("assistant", "earlier answer"), ("user", "my question")]
    win._sent_text = "my question"
    win._streaming = "a partial ans"
    win._cancelling = True

    win._undo_send()

    assert win._messages == [("assistant", "earlier answer")]
    assert win._input.toPlainText() == "my question"
    assert win._streaming == ""          # the partial answer is discarded
    assert win._cancelling is False


def test_an_interrupted_turn_undoes_instead_of_keeping_the_partial(win):
    """interrupt() emits turn_finished, NOT turn_failed - so the finish handler
    is where a cancel actually lands."""
    win._messages = [("user", "my question")]
    win._sent_text = "my question"
    win._cancelling = True

    win._on_turn_finished("a partial answer that streamed in")

    assert win._messages == []
    assert win._input.toPlainText() == "my question"


def test_a_normal_turn_still_keeps_its_answer(win):
    win._messages = [("user", "my question")]
    win._cancelling = False

    win._on_turn_finished("the real answer")

    assert win._messages == [("user", "my question"), ("assistant", "the real answer")]
    assert win._input.toPlainText() == ""


def test_a_failure_during_a_cancel_also_undoes(win):
    win._messages = [("user", "my question")]
    win._sent_text = "my question"
    win._cancelling = True

    win._on_turn_failed("process died")

    assert win._messages == []                       # no error bubble either
    assert win._input.toPlainText() == "my question"
