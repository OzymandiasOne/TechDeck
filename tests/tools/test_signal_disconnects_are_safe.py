"""Every signal `disconnect` goes through `sdk`-style single home: `safe_disconnect`.

Reported 2026-10-06 from a healthy startup log: ~20 copies of

    audio_manager.py:197: RuntimeWarning: Failed to disconnect
    (<function AudioManager.play.<locals>._on_status ...>) from signal
    "statusChanged()".

Two defects behind it, both of the same class.

1. **A failed `disconnect` in PySide6 does not raise.** It writes a
   `RuntimeWarning` to stderr and returns False. So

       try:
           sig.disconnect(slot)
       except (RuntimeError, TypeError):
           pass

   looks defensive and silences nothing -- the `except` never runs. Every
   audio one-shot that was already Ready (the common case once Qt has the WAV
   cached) printed two console lines. A log that cries wolf every boot is a
   log nobody reads when something real happens.

2. **Chaining several disconnects inside ONE `try` loses the rest.** In
   `update_dialog` and java_tutor's `claude_session`, if the first signal had
   nothing attached the remaining disconnects were skipped -- and in
   `claude_session` the skipped one was `finished`, whose slot nulls out the
   replacement process. That one was a live bug, not noise.

`techdeck.core.qt_signals.safe_disconnect` is the single home: it swallows
both the exception and the warning, handles one slot or all, and is called
unconditionally so there is no wiring state to guess. This gate keeps raw
`.disconnect(` out of the tree so the class cannot ship again.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TREES = ("techdeck", "plugins", "tools/devkit")

# The helper itself is the one place allowed to call the real thing.
HOME = ROOT / "techdeck" / "core" / "qt_signals.py"

# `x.disconnect(` on anything, but not our own helper call and not a plain
# `safe_disconnect(` definition/use.
RAW_DISCONNECT = re.compile(r"(?<!safe_)\bdisconnect\s*\(")


def _py_files():
    for tree in TREES:
        base = ROOT / tree
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if path == HOME or "__pycache__" in path.parts:
                continue
            yield path


def test_no_raw_signal_disconnect():
    offenders = []
    for path in _py_files():
        for n, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if RAW_DISCONNECT.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{n}: {stripped}")
    assert not offenders, (
        "Raw signal .disconnect() found. PySide6 WARNS instead of raising on a "
        "failed disconnect, so a try/except around it silences nothing. Use "
        "techdeck.core.qt_signals.safe_disconnect(signal[, slot]) -- one call "
        "per signal, never several in one try:\n  " + "\n  ".join(offenders)
    )


def test_safe_disconnect_is_quiet_and_honest():
    """It must not raise, must not print, and must report what happened."""
    import warnings

    from PySide6.QtCore import QObject, Signal

    from techdeck.core.qt_signals import safe_disconnect

    class Thing(QObject):
        fired = Signal()

    thing = Thing()

    def slot():
        pass

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        # Never connected: a no-op, and silent.
        assert safe_disconnect(thing.fired, slot) is False
        # Connected: actually unhooks, and says so.
        thing.fired.connect(slot)
        assert safe_disconnect(thing.fired, slot) is True
        # Twice is harmless.
        assert safe_disconnect(thing.fired, slot) is False
        # No-slot form, with nothing attached.
        assert safe_disconnect(thing.fired) is False
    assert not [w for w in caught if w.category is RuntimeWarning], (
        "safe_disconnect leaked a RuntimeWarning to the console"
    )
