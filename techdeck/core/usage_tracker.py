"""
TechDeck Usage Tracker
======================
Silent, best-effort usage telemetry. Records one row per SUCCESSFUL plugin
run — who (Windows user, from their home directory), when, which app, how
long — so adoption and time-saved impact can be measured without asking
anyone to self-report.

Why webhook + local spool (and not a shared SharePoint workbook):

* There is NO single SharePoint location all users can access (3 branches +
  QA sync different sites), so a shared synced workbook can't reach everyone.
* Even where access exists, 15 users appending to one synced xlsx forks it
  into OneDrive conflict copies (silent row loss) — the feedback workbook
  tolerates that only because submissions are rare.
* Outbound HTTPS to a Power Automate webhook is proven from every user's
  network (922 Setup posts its Planner cards that way) and needs ZERO
  per-machine setup: the flow appends rows to an Excel file in the
  maintainer's own OneDrive, serializing all writers. Flow recipe:
  docs/USAGE_TELEMETRY.md.

Data flow, per successful run:

  1. Append one row to the LOCAL spool CSV
     (%LOCALAPPDATA%/TechDeck/usage/usage_log.csv) — the machine's own
     source of truth. Created at runtime (never shipped by the installer,
     so updates can't overwrite it); survives app updates like settings.json.
  2. If TELEMETRY_WEBHOOK_URL is configured, POST every not-yet-delivered
     spool row (a cursor file tracks how many rows have been delivered) to
     the flow. Offline / webhook down → rows simply wait; the backlog
     flushes on a later successful run. Delivery is at-least-once: a reply
     lost after the flow processed a batch re-sends it, and duplicate rows
     are collapsed on the maintainer's side.
  3. The debug report bundles the full spool (see debug_report.py), so a
     bug report also hand-delivers the machine's usage history — the
     backstop channel when the webhook has never been reachable.

Silence contract: record_run() never raises, never blocks the caller (all
I/O happens on a daemon thread), and never writes to the console. Failures
go to the run log file only (plugin_runs.log), which the debug report
already collects.
"""

from __future__ import annotations

import csv
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import List

from techdeck.core.constants import APP_VERSION, TELEMETRY_WEBHOOK_URL

# Spool schema. Order matters: the debug report and the Power Automate flow
# recipe (docs/USAGE_TELEMETRY.md) both mirror it.
SPOOL_HEADERS = [
    "Timestamp", "User", "Machine", "Plugin ID", "Plugin Name",
    "Family", "Duration (s)", "TechDeck Version",
]

_TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S"  # lexicographically sortable
_POST_TIMEOUT_S = 15
_MAX_EVENTS_PER_POST = 200

# Serializes spool/cursor access across tracker threads in this process.
_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Paths / identity
# ---------------------------------------------------------------------------

def usage_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    return base / "TechDeck" / "usage"


def spool_path() -> Path:
    return usage_dir() / "usage_log.csv"


def _cursor_path() -> Path:
    return usage_dir() / "sent_cursor.txt"


def local_user() -> str:
    """The Windows user, pulled from their home directory name."""
    return Path.home().name


def _machine() -> str:
    return os.environ.get("COMPUTERNAME") or "unknown"


def _quiet_logger():
    # Lazy import: plugin_executor imports this module (function-level) too.
    from techdeck.core.plugin_executor import get_run_logger
    return get_run_logger()


# ---------------------------------------------------------------------------
# Spool + cursor
# ---------------------------------------------------------------------------

def _append_spool(row: List) -> None:
    path = spool_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new_file:
            writer.writerow(SPOOL_HEADERS)
        writer.writerow(row)


def read_spool_rows() -> List[List[str]]:
    """All data rows (header excluded). Also used by the debug report."""
    path = spool_path()
    if not path.exists():
        return []
    with open(path, "r", newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    return [r for r in rows[1:] if r]


def sent_count() -> int:
    """How many spool rows have been delivered to the webhook."""
    try:
        return max(0, int(_cursor_path().read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):
        return 0


def _set_sent_count(n: int) -> None:
    _cursor_path().write_text(str(n), encoding="utf-8")


# ---------------------------------------------------------------------------
# Webhook delivery
# ---------------------------------------------------------------------------

def _post_events(kind: str, events: List[dict]) -> bool:
    """POST a batch to the Power Automate flow. True on HTTP 2xx."""
    import requests  # lazy: keep module import light for the debug report
    payload = {
        "type": kind,
        "source": "TechDeck",
        "techdeck_version": APP_VERSION,
        "events": events,
    }
    resp = requests.post(TELEMETRY_WEBHOOK_URL, json=payload,
                         timeout=_POST_TIMEOUT_S)
    return 200 <= resp.status_code < 300


def _row_to_event(row: List[str]) -> dict:
    keys = ["timestamp", "user", "machine", "plugin_id", "plugin_name",
            "family", "duration_s", "techdeck_version"]
    return {k: (row[i] if i < len(row) else "") for i, k in enumerate(keys)}


def _flush_backlog() -> None:
    """Send every undelivered spool row, advancing the cursor per batch."""
    if not TELEMETRY_WEBHOOK_URL:
        return
    rows = read_spool_rows()
    cursor = min(sent_count(), len(rows))
    while cursor < len(rows):
        batch = rows[cursor:cursor + _MAX_EVENTS_PER_POST]
        if not _post_events("usage", [_row_to_event(r) for r in batch]):
            raise RuntimeError("webhook returned a non-2xx status")
        cursor += len(batch)
        _set_sent_count(cursor)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record_run(plugin_id: str, plugin_name: str, family: str,
               duration_seconds: float) -> None:
    """Record one successful plugin run. Fire-and-forget: returns
    immediately, never raises, never touches the console."""
    try:
        row = [
            datetime.now().strftime(_TIMESTAMP_FMT),
            local_user(),
            _machine(),
            plugin_id,
            plugin_name,
            family,
            round(float(duration_seconds), 1),
            APP_VERSION,
        ]
        threading.Thread(target=_record, args=(row,),
                         name="UsageTracker", daemon=True).start()
    except Exception:
        pass


def _record(row: List) -> None:
    with _LOCK:
        try:
            _append_spool(row)
        except Exception as exc:
            try:
                _quiet_logger().info("USAGE spool append failed: %s", exc)
            except Exception:
                pass
            return
        try:
            _flush_backlog()
        except Exception as exc:
            # Expected whenever offline / webhook unreachable — the backlog
            # just waits for the next run. File-log only; console stays clean.
            try:
                _quiet_logger().info("USAGE webhook flush deferred: %s", exc)
            except Exception:
                pass


def send_feedback_event(suggestion: str, which_feature: str) -> None:
    """Deliver one feedback submission through the same flow. Unlike usage
    telemetry this is user-facing and interactive, so it RAISES on failure
    (no webhook configured, network error, non-2xx) — the feedback dialog
    turns that into a visible error and the user can retry."""
    if not TELEMETRY_WEBHOOK_URL:
        raise RuntimeError("no telemetry webhook configured in this build")
    event = {
        "timestamp": datetime.now().strftime(_TIMESTAMP_FMT),
        "user": local_user(),
        "machine": _machine(),
        "suggestion": suggestion,
        "which_feature": which_feature,
        "techdeck_version": APP_VERSION,
    }
    if not _post_events("feedback", [event]):
        raise RuntimeError("the feedback service returned an error status")


def post_triage_events(events: List[dict]) -> bool:
    """POST DevKit Dev Board triage decisions (Status updates for existing
    Feedback rows) through the same flow — the flow's triage branch matches
    each event's ``row_key`` against the FeedbackTable's Key column and sets
    the Status cell server-side, so the maintainer's machine never writes the
    workbook locally (docs/USAGE_TELEMETRY.md). Maintainer machine only.
    Returns True on 2xx; network failures raise for the caller to surface."""
    if not TELEMETRY_WEBHOOK_URL:
        return False
    return _post_events("triage", events)


def telemetry_status() -> dict:
    """Snapshot for the debug report — never raises."""
    out = {
        "webhook_configured": bool(TELEMETRY_WEBHOOK_URL),
        "spool_path": str(spool_path()),
        "rows": 0, "sent": 0, "pending": 0,
    }
    try:
        rows = read_spool_rows()
        sent = min(sent_count(), len(rows))
        out.update(rows=len(rows), sent=sent, pending=len(rows) - sent)
    except Exception as exc:
        out["error"] = str(exc)
    return out
