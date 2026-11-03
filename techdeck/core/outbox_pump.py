"""
The outbox pump
===============
Drains `flow_client`'s command queues in the background, once per launch.

WHY THIS EXISTS (2026-10-21). `flow_client` shipped a complete, tested outbox
in v0.8.8 - `queue_command`, `read_outbox`, `flush_outbox`, `outbox_depth` -
and **nothing in TechDeck ever called `flush_outbox`.** Defined, re-exported
through the SDK, zero call sites. So "queue it and we'll deliver it later" was
a promise the app could not keep: a queued command sat in a JSONL file nobody
read, forever.

That made the outbox *worse* than no outbox for anything a person wrote. The
feedback dialog's old behaviour was a LOUD failure - an error dialog, with the
text still in the box so they could retry. Routing it through an unpumped
queue would have turned that into a silent one: a cheerful "Thanks!", 25
tickets paid out, and a suggestion that never existed as far as anyone could
tell. Found while planning exactly that change.

Design, and the reasons for each part:

* **A daemon thread, never the UI thread.** `flush_outbox`'s default limit is
  25 and the default timeout is 20 s, so a worst-case flush is 500 seconds of
  frozen application. The E-FLOW-1 gate stops a flow call going inside a
  `for` loop; nothing stops one going on the GUI thread.
* **A small limit and a short timeout.** Five per command at 10 s. A backlog
  drains over a few launches instead of holding one launch hostage; the queue
  is not urgent by definition - it exists because the first attempt failed.
* **Once per launch, not a poll.** Every command in every queue already
  carries its own delivery address, so there is nothing to coordinate and
  nothing to schedule. Repeated polling would also burn the flow licence's
  request budget for no benefit.
* **Discovered, not registered.** The pump scans the outbox directory rather
  than holding a list of known commands, so a new two-way feature is drained
  the day it ships without anyone remembering to add it here.
* **Silent on success, file-log on failure.** A delivery the user never knew
  was pending must not announce itself in their console.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, List, Optional, Tuple

from techdeck.core import flow_client

__all__ = ["start", "pump_now", "pending_commands", "total_pending"]

logger = logging.getLogger(__name__)

# Deliberately smaller than flow_client's defaults. See the module docstring:
# the queue is never urgent, and a launch must never wait on it.
PUMP_LIMIT = 5
PUMP_TIMEOUT_S = 10.0

_started = threading.Event()


def pending_commands() -> List[str]:
    """Every command name with at least one envelope waiting.

    Discovered from disk so a new two-way feature needs no registration here.
    """
    out_dir = flow_client.flow_dir() / "outbox"
    try:
        if not out_dir.is_dir():
            return []
        return sorted(p.stem for p in out_dir.glob("*.jsonl")
                      if flow_client.outbox_depth(p.stem) > 0)
    except OSError:
        return []


def total_pending() -> int:
    """How many commands are waiting across every queue - for a Settings line."""
    try:
        return sum(flow_client.outbox_depth(c) for c in pending_commands())
    except Exception:
        return 0


def pump_now(*, log: Optional[Callable[[str], None]] = None) -> Tuple[int, int]:
    """Drain every queue once, on THIS thread. Returns (delivered, waiting).

    Never raises. Callers are background threads and shutdown paths; an
    exception here must not take down whatever asked.
    """
    delivered = waiting = 0
    for command in pending_commands():
        try:
            sent, left = flow_client.flush_outbox(
                command, log=log, timeout=PUMP_TIMEOUT_S, limit=PUMP_LIMIT)
            delivered += sent
            waiting += left
        except Exception as exc:
            # Expected while offline or behind a blocked proxy. The envelopes
            # stay queued; the next launch tries again.
            logger.info("Outbox flush deferred for '%s': %s", command, exc)
    if delivered:
        logger.info("Outbox pump delivered %d command(s); %d still waiting.",
                    delivered, waiting)
    return (delivered, waiting)


def start() -> None:
    """Kick one pump pass on a daemon thread. Safe to call more than once;
    only the first call in a process does anything."""
    if _started.is_set():
        return
    _started.set()
    try:
        threading.Thread(target=_run, name="OutboxPump", daemon=True).start()
    except Exception as exc:                                   # pragma: no cover
        logger.info("Could not start the outbox pump: %s", exc)


def _run() -> None:
    try:
        pending = pending_commands()
        if not pending:
            return
        logger.info("Outbox pump starting: %s", ", ".join(pending))
        pump_now()
    except Exception as exc:                                   # pragma: no cover
        logger.info("Outbox pump failed: %s", exc)


def _reset_for_tests() -> None:
    """Let a test start the pump again in the same process."""
    _started.clear()
