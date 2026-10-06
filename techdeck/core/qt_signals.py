"""Signal housekeeping helpers.

Why this module exists: **a failed `disconnect` in PySide6 does not raise --
it prints a `RuntimeWarning` to stderr and returns False.** So the idiom

    try:
        sig.disconnect(slot)
    except (RuntimeError, TypeError):
        pass

looks defensive and is not: the `except` never fires, and every failed
disconnect still writes two lines to the console. TechDeck's audio one-shots
hit this on the already-Ready fast path (the handler was never connected, so
there is nothing to unhook), which put ~20 identical warnings in the startup
log of a perfectly healthy app. A console that cries wolf every boot is a
console nobody reads when something real happens.

`safe_disconnect` is the single home for "unhook this if it is hooked". It
swallows the exception AND the warning, and tells you which it was.
"""

from __future__ import annotations

import warnings
from typing import Any, Callable, Optional

__all__ = ["safe_disconnect"]


def safe_disconnect(signal: Any, slot: Optional[Callable] = None) -> bool:
    """Disconnect `slot` from `signal` (or every slot, if `slot` is None).

    Returns True if something was actually disconnected. Never raises and
    never prints: a signal that was not connected is an ordinary outcome, not
    a defect. Call it unconditionally instead of guessing the wiring state.
    """
    try:
        with warnings.catch_warnings():
            # The failure mode this module exists for.
            warnings.simplefilter("ignore", RuntimeWarning)
            result = signal.disconnect() if slot is None \
                else signal.disconnect(slot)
    except (RuntimeError, TypeError):
        return False
    # PySide6 returns None on success for some signal types, False on a
    # no-op disconnect. Treat only an explicit False as "nothing to do".
    return result is not False
