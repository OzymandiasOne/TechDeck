"""
TechDeck Two-Way Flow Client
============================
The ONE place TechDeck asks a Power Automate flow a question and reads the
answer. Premium ("When an HTTP request is received" + "Response") made this
possible; before it, every flow call was a shout into the dark -- which is why
Batch 488's cards all died in the flow while TechDeck logged DONE
(docs/TEAMS_CARDS.md).

Rules this module exists to enforce (docs/TWO_WAY_FLOW_CLIENT.md, and the
`techdeck-flows` skill section 3):

* **A flow call is an upgrade, never a dependency.** Every call takes a
  timeout and a FALLBACK, and `ask_flow` NEVER raises. If the flow is down,
  offline, or slow, the caller gets its fallback and the app carries on doing
  what it did before two-way flows existed.
* **One answer shape for every flow:**
  ``{"ok": bool, "reason": "<machine word>", "message": "<for a person>",
     "data": {...}}``
  A rejection is a normal answer (``ok: false``) -- not an HTTP error. HTTP
  errors mean the flow itself broke.
* **Every command carries a `command_id` (UUID).** Delivery is at-least-once,
  so the flow must recognise a repeat and answer as it did the first time.
  A queued command keeps its ORIGINAL id across every retry -- that is what
  makes the retry safe.
* **Writes go through the outbox** (`queue_command` + `flush_outbox`), the
  same queue-locally-deliver-later pattern as the usage spool. **Reads come
  from `cache_get`**, which a successful call refreshes, so a read still
  answers (stale, and it says so) with the flow down.
* **Never call in a loop.** 1-5 s per call, 120 s hard platform cap. A long
  job answers at once with a job id and the app asks again later. Enforced by
  tests/tools/test_no_flow_calls_in_loops.py.

In a 922 sandbox run nothing is sent: the envelope is previewed and the
caller gets its fallback, exactly as if the flow were unreachable.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Mapping, NamedTuple, Optional, Tuple

# The platform's own ceiling: a request trigger cannot answer after 120 s.
MAX_TIMEOUT_S = 120.0
DEFAULT_TIMEOUT_S = 20.0

# A NamedTuple's default is ONE shared object, so a plain {} here would let
# `answer.data["x"] = 1` in any caller poison every later default-data answer.
# Read-only, so that mistake raises instead of rotting silently.
_NO_DATA: Mapping[str, Any] = MappingProxyType({})

# Serializes outbox/cache file access across threads in this process.
_LOCK = threading.RLock()


# -----------------------------------------------------------------------------
# The answer
# -----------------------------------------------------------------------------

class FlowAnswer(NamedTuple):
    """What came back (or what we fell back to).

    `reached` is the honest bit and the one callers most often want: False
    means we never got a decision out of the flow, so this is a fallback and
    nothing was decided. `ok` is the flow's VERDICT -- False with
    `reached=True` is a real, deliberate "no".
    """
    ok: bool
    reason: str = ""
    message: str = ""
    data: Mapping[str, Any] = _NO_DATA
    reached: bool = False
    command_id: str = ""
    status: int = 0

    @property
    def rejected(self) -> bool:
        """The flow answered and said no (as opposed to never answering)."""
        return self.reached and not self.ok


# Machine `reason` words this module produces itself. A flow may return any
# other word; these are ours, so callers can branch on them.
REASON_UNREACHABLE = "unreachable"   # network/proxy/timeout -- never arrived
REASON_FLOW_ERROR = "flow_error"     # non-2xx: the flow itself broke
REASON_BAD_ANSWER = "bad_answer"     # 2xx, but not the contract shape
REASON_NO_ANSWER = "no_answer"       # 2xx, no answer, and none was expected
REASON_NOT_CONFIGURED = "not_configured"   # no URL set for this command
REASON_SANDBOX = "sandbox"           # sandbox run: deliberately not sent
REASON_DRY_RUN = "dry_run"           # caller asked for a preview only

# `bad_answer` vs `no_answer` is the whole migration story. A flow that has
# not been given its Response action yet returns a bare 2xx, and that is
# CORRECT for it -- the app simply learns nothing, exactly as before. Calling
# that an error would print a scary line on every card post until all four
# flows are upgraded. A flow we KNOW answers returning nothing readable is a
# real fault, and that one stays `bad_answer`.


# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

def flow_dir() -> Path:
    """%LOCALAPPDATA%/TechDeck/flows -- created at runtime, never shipped by
    the installer, so an update cannot wipe a pending outbox."""
    base = Path(os.environ.get("LOCALAPPDATA") or str(Path.home()))
    return base / "TechDeck" / "flows"


def outbox_path(command: str) -> Path:
    return flow_dir() / "outbox" / f"{_safe_name(command)}.jsonl"


def cache_path(key: str) -> Path:
    return flow_dir() / "cache" / f"{_safe_name(key)}.json"


def _safe_name(name: str) -> str:
    """A command/cache name as a safe single filename component."""
    cleaned = "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(name))
    return cleaned.strip("_") or "unnamed"


def _mkdir(path: Path) -> None:
    # Function-level import: plugin_sdk imports THIS module, so a top-level
    # import of plugin_sdk would be circular. ensure_dir applies long_path.
    from techdeck.core.plugin_sdk import ensure_dir
    ensure_dir(path)


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

def _logger(log: Optional[Callable[[str], None]]) -> Callable[[str], None]:
    """A plugin's console callback, or the run log when there is none. A flow
    call must never die because logging failed."""
    if callable(log):
        def _safe(msg: str) -> None:
            try:
                log(msg)
            except Exception:
                pass
        return _safe

    def _quiet(msg: str) -> None:
        try:
            from techdeck.core.plugin_executor import get_run_logger
            get_run_logger().info("FLOW %s", msg)
        except Exception:
            pass
    return _quiet


# -----------------------------------------------------------------------------
# The envelope -- the REMOTE CONTRACT every two-way flow parses
#
# Every key below is read by the flows. Pinned by
# tests/core/test_flow_client.py::test_envelope_carries_every_contract_key --
# a refactor that drops one of these takes every two-way flow down at once.
# -----------------------------------------------------------------------------

ENVELOPE_KEYS = ("command", "command_id", "sent_at", "app_version",
                 "user", "machine", "data")


def build_envelope(command: str, data: Optional[dict] = None,
                   command_id: str = "") -> Dict[str, Any]:
    """The one place a two-way request is assembled. Never build this inline
    at a call site (the Batch 488 lesson: one assembler, pinned by a test)."""
    from techdeck.core.constants import APP_VERSION
    return {
        "command": str(command),
        "command_id": command_id or new_command_id(),
        "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "app_version": APP_VERSION,
        "user": _local_user(),
        "machine": os.environ.get("COMPUTERNAME") or "unknown",
        # Always an object, never absent: a flow reading data?['x'] on a null
        # body is a hard FAIL, not a skip.
        "data": dict(data or {}),
    }


def new_command_id() -> str:
    return str(uuid.uuid4())


def _local_user() -> str:
    """The Windows user, from their home directory name (matches the usage
    spool's `User` column, so rows can be joined)."""
    return Path.home().name


# -----------------------------------------------------------------------------
# Asking
# -----------------------------------------------------------------------------

def ask_flow(url: str, command: str, data: Optional[dict] = None, *,
             fallback: Any = None,
             log: Optional[Callable[[str], None]] = None,
             timeout: float = DEFAULT_TIMEOUT_S,
             command_id: str = "",
             cache_key: str = "",
             dry_run: bool = False) -> FlowAnswer:
    """Ask a two-way flow one question and return its answer.

    NEVER raises, and never blocks longer than `timeout`. When the flow cannot
    be reached the answer is built from `fallback` with `reached=False`, so the
    caller's old behaviour is one `if not answer.reached:` away.

    `fallback` may be a FlowAnswer (full control) or a dict (becomes `data`).
    `cache_key`, when given, stores a successful answer's `data` so a later
    call can read it with `cache_get` while the flow is down.
    `dry_run` previews the envelope and returns the fallback without sending.
    """
    say = _logger(log)
    timeout = max(1.0, min(float(timeout or DEFAULT_TIMEOUT_S), MAX_TIMEOUT_S))
    envelope = build_envelope(command, data, command_id)
    cid = envelope["command_id"]

    url = (url or "").strip()
    if not url:
        say(f"No flow URL is configured for '{command}' - using the fallback.")
        return _fallback_answer(fallback, REASON_NOT_CONFIGURED, cid,
                                "No flow address is configured for this feature.")

    sandbox = _sandbox_root()
    if sandbox is not None or dry_run:
        label = "SANDBOX" if sandbox is not None else "DRY RUN"
        say(f"{label}: '{command}' NOT sent - envelope previewed instead.")
        _preview(envelope, command, say)
        reason = REASON_SANDBOX if sandbox is not None else REASON_DRY_RUN
        return _fallback_answer(fallback, reason, cid,
                                f"{label}: nothing was sent to the flow.")

    answer = _post(url, envelope, timeout, say, label=command)
    if answer.reached and answer.ok and cache_key:
        cache_put(cache_key, answer.data)
    if not answer.reached:
        return _fallback_answer(fallback, answer.reason, cid, answer.message,
                                status=answer.status)
    return answer


def post_payload(url: str, payload: dict, *, label: str = "",
                 log: Optional[Callable[[str], None]] = None,
                 timeout: float = DEFAULT_TIMEOUT_S,
                 expect_answer: bool = True) -> FlowAnswer:
    """POST `payload` **verbatim** and read a contract answer if one comes back.

    `ask_flow` is the front door for a NEW two-way flow: it wraps the caller's
    data in the envelope. This is the door for a flow that already has its own
    payload shape — the four card flows — where wrapping it would break the
    live flow and every installed TechDeck pointed at it.

    `expect_answer=False` says the flow may still be the one-way kind. A bare
    2xx is then reported as `no_answer` and logged as "accepted", not as a
    fault: that is the correct behaviour for a flow whose Response action has
    not been added yet.

    Honours the 922 sandbox the same way `post_webhook` does — nothing is
    sent, the payload is previewed, and the caller carries on as after a real
    post. Without that, a sandbox run against Batch 900 would write real cards
    onto the live Planner board.
    """
    say = _logger(log)
    timeout = max(1.0, min(float(timeout or DEFAULT_TIMEOUT_S), MAX_TIMEOUT_S))

    if _sandbox_root() is not None:
        say(f"SANDBOX: the '{label or 'flow'}' post was NOT sent - "
            f"payload previewed instead.")
        _preview(payload, label or "payload", say)
        return FlowAnswer(ok=False, reason=REASON_SANDBOX,
                          message="Sandbox run: nothing was sent to the flow.")

    if not (url or "").strip():
        say(f"No webhook URL is configured for '{label or 'this post'}'.")
        return FlowAnswer(ok=False, reason=REASON_NOT_CONFIGURED,
                          message="No flow address is configured.")

    return _post(url.strip(), payload, timeout, say, label=label,
                 expect_answer=expect_answer)


def _post(url: str, envelope: dict, timeout: float,
          say: Callable[[str], None], *, label: str = "",
          expect_answer: bool = True) -> FlowAnswer:
    """One HTTP round trip, turned into a FlowAnswer. `reached` is True only
    when the flow returned a contract-shaped answer. `label` names the flow in
    the log lines (a raw card payload has no `command` to name itself with)."""
    cid = envelope.get("command_id", "")
    command = label or envelope.get("command", "") or "flow"

    import requests

    try:
        resp = requests.post(url, json=envelope, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        say(f"ERROR: could not reach the '{command}' flow: {exc}")
        say("Check your network/VPN and that the flow is on. Carrying on without it.")
        return FlowAnswer(ok=False, reason=REASON_UNREACHABLE, command_id=cid,
                          message="Could not reach the flow.")

    if not (200 <= resp.status_code < 300):
        say(f"ERROR: the '{command}' flow returned HTTP {resp.status_code}.")
        say(f"Response: {(resp.text or '')[:500]}")
        return FlowAnswer(ok=False, reason=REASON_FLOW_ERROR, command_id=cid,
                          status=resp.status_code,
                          message=f"The flow failed (HTTP {resp.status_code}).")

    try:
        body = resp.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or "ok" not in body:
        if not expect_answer:
            # A one-way flow that has not been taught to answer yet. It took
            # the message; that is all it was ever going to tell us.
            say(f"The '{command}' flow accepted the request "
                f"(HTTP {resp.status_code}). It does not report back yet.")
            return FlowAnswer(ok=False, reason=REASON_NO_ANSWER, command_id=cid,
                              status=resp.status_code,
                              message="The flow accepted the request, but "
                                      "cannot say what it did with it.")
        say(f"ERROR: the '{command}' flow answered, but not in the agreed shape.")
        say(f"Response: {(resp.text or '')[:500]}")
        return FlowAnswer(ok=False, reason=REASON_BAD_ANSWER, command_id=cid,
                          status=resp.status_code,
                          message="The flow's answer could not be understood.")

    payload = body.get("data")
    answer = FlowAnswer(
        ok=bool(body.get("ok")),
        reason=str(body.get("reason") or ""),
        message=str(body.get("message") or ""),
        data=payload if isinstance(payload, dict) else {},
        reached=True,
        command_id=str(body.get("command_id") or cid),
        status=resp.status_code,
    )
    verdict = "OK" if answer.ok else f"declined ({answer.reason or 'no reason given'})"
    say(f"The flow answered: {verdict}.")
    if answer.message:
        say(f"  {answer.message}")
    return answer


def _fallback_answer(fallback: Any, reason: str, command_id: str,
                     message: str, status: int = 0) -> FlowAnswer:
    """Turn a caller's fallback into an answer. `reached` is always False --
    nothing was decided by the flow, and a caller must be able to tell."""
    if isinstance(fallback, FlowAnswer):
        return fallback._replace(reached=False,
                                 command_id=fallback.command_id or command_id,
                                 reason=fallback.reason or reason,
                                 message=fallback.message or message)
    return FlowAnswer(ok=False, reason=reason, message=message,
                      data=dict(fallback) if isinstance(fallback, dict) else {},
                      reached=False, command_id=command_id, status=status)


def _sandbox_root():
    from techdeck.core.plugin_sdk import sandbox_922_root
    return sandbox_922_root()


def _preview(envelope: dict, command: str, say: Callable[[str], None]) -> None:
    from techdeck.core.plugin_sdk import write_payload_preview
    write_payload_preview(envelope, f"last_flow_{_safe_name(command)}.json", say)


# -----------------------------------------------------------------------------
# The outbox -- every WRITE goes through here
#
# Queue first, deliver after. A write the user already saw accepted must not
# be lost because the network blinked, and a command that may have arrived
# must be safe to send again: the queued envelope keeps its original
# command_id forever, so the flow recognises the repeat.
# -----------------------------------------------------------------------------

def queue_command(url: str, command: str, data: Optional[dict] = None, *,
                  command_id: str = "",
                  log: Optional[Callable[[str], None]] = None) -> str:
    """Append one command to its outbox and return its command_id. Never
    raises: a failed queue write is logged, not thrown at the caller."""
    say = _logger(log)
    envelope = build_envelope(command, data, command_id)
    envelope["url"] = (url or "").strip()
    path = outbox_path(command)
    try:
        with _LOCK:
            _mkdir(path.parent)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(envelope) + "\n")
    except OSError as exc:
        say(f"(Could not queue '{command}': {exc})")
    return envelope["command_id"]


def read_outbox(command: str) -> List[Dict[str, Any]]:
    """Every queued envelope for `command`, oldest first. A corrupt line is
    skipped rather than killing the flush -- a half-written line from a crash
    must not strand the whole queue behind it."""
    path = outbox_path(command)
    out: List[Dict[str, Any]] = []
    try:
        with _LOCK:
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def _write_outbox(command: str, items: List[Dict[str, Any]]) -> None:
    path = outbox_path(command)
    try:
        with _LOCK:
            if not items:
                if path.exists():
                    path.unlink()
                return
            _mkdir(path.parent)
            with open(path, "w", encoding="utf-8") as fh:
                for item in items:
                    fh.write(json.dumps(item) + "\n")
    except OSError:
        pass


def flush_outbox(command: str, url: str = "", *,
                 log: Optional[Callable[[str], None]] = None,
                 timeout: float = DEFAULT_TIMEOUT_S,
                 limit: int = 25) -> Tuple[int, int]:
    """Deliver queued commands. Returns (delivered, still_waiting).

    A command is DELIVERED once the flow decided it -- `ok: false` is a
    decision, so it leaves the queue too (re-sending a rejected command just
    gets it rejected again, forever). Only never-answered calls stay queued,
    and the first UNREACHABLE one stops the flush: if the flow is down for one
    it is down for all, and hammering it only wastes the user's time.
    """
    say = _logger(log)
    pending = read_outbox(command)
    if not pending:
        return (0, 0)
    if _sandbox_root() is not None:
        say(f"SANDBOX: {len(pending)} queued '{command}' command(s) NOT sent.")
        return (0, len(pending))

    delivered = 0
    left: List[Dict[str, Any]] = []
    for i, envelope in enumerate(pending):
        target = (envelope.pop("url", "") or url or "").strip()
        if i >= limit:
            envelope["url"] = target
            left.append(envelope)
            continue
        if not target:
            # Nowhere to send it, and nowhere it will ever go. Dropping it
            # beats a queue that grows forever.
            say(f"(Dropping a queued '{command}' with no flow address.)")
            delivered += 1
            continue
        answer = _post(target, envelope, timeout, say)
        if answer.reached:
            delivered += 1
            continue
        envelope["url"] = target
        left.append(envelope)
        if answer.reason == REASON_UNREACHABLE:
            # Keep the rest untried, in order.
            left.extend(_restore(pending[i + 1:], url))
            break
    _write_outbox(command, left)
    if delivered:
        say(f"Delivered {delivered} queued '{command}' command(s).")
    if left:
        say(f"{len(left)} '{command}' command(s) are waiting for the flow.")
    return (delivered, len(left))


def _restore(items: List[Dict[str, Any]], url: str) -> List[Dict[str, Any]]:
    """Re-attach the url to envelopes a stopped flush never tried."""
    out = []
    for item in items:
        item.setdefault("url", (url or "").strip())
        out.append(item)
    return out


def outbox_depth(command: str) -> int:
    """How many commands are waiting -- for a status line or the debug report."""
    return len(read_outbox(command))


# -----------------------------------------------------------------------------
# The read cache
#
# A read must still answer with the flow down. A successful call refreshes the
# cache; `cache_get` hands back the last good answer AND its age, so a caller
# can say "as of 20 minutes ago" instead of pretending it is live.
# -----------------------------------------------------------------------------

def cache_put(key: str, data: Optional[Mapping[str, Any]]) -> None:
    """Store one answer's data. Best effort: a cache that cannot be written is
    a slower app, not a broken one."""
    path = cache_path(key)
    record = {"stored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "data": dict(data or {})}
    try:
        with _LOCK:
            _mkdir(path.parent)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(record, fh, indent=2)
    except OSError:
        pass


def cache_get(key: str, max_age_s: Optional[float] = None
              ) -> Optional[Tuple[Dict[str, Any], float]]:
    """The cached data and its age in seconds, or None when there is nothing
    cached (or it is older than `max_age_s`)."""
    path = cache_path(key)
    try:
        with _LOCK:
            with open(path, "r", encoding="utf-8") as fh:
                record = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    data = record.get("data")
    if not isinstance(data, dict):
        return None
    age = _age_seconds(record.get("stored_at"))
    if max_age_s is not None and age > float(max_age_s):
        return None
    return (data, age)


def _age_seconds(stored_at: Any) -> float:
    try:
        when = datetime.fromisoformat(str(stored_at))
    except (TypeError, ValueError):
        return float("inf")
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - when).total_seconds())


def cache_clear(key: str) -> None:
    try:
        with _LOCK:
            path = cache_path(key)
            if path.exists():
                path.unlink()
    except OSError:
        pass


# Plugin-facing aliases. Inside a plugin, `sdk.cache_get(...)` reads like a
# generic cache; `sdk.flow_cache_get(...)` says which cache it is.
flow_cache_put = cache_put
flow_cache_get = cache_get
flow_cache_clear = cache_clear
