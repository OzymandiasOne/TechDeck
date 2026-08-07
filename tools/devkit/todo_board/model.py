"""Data layer for the DevKit Dev Board.

Two jobs:

1. Read feedback rows from the maintainer's telemetry workbook (the ``Feedback``
   and ``Archive`` sheets of ``TechDeck Telemetry.xlsx``) into ``FeedbackEntry``
   records — resiliently, so a workbook that's open in Excel or cloud-only gives
   a clear status instead of a crash (Hard Rule 13).

2. Own the persistent board overlay in
   ``%LOCALAPPDATA%/TechDeck/devkit/todo_board.json`` — the buckets, and each
   card's placement, checklist, and labels. New feedback rows sync IN (live rows
   to To-Do, archived rows to Done) without ever disturbing cards you've already
   organised. Each card snapshots its source fields at creation, so a card
   survives even if its telemetry row is later edited, archived, or deleted.

3. Write STATUS back (``flush_writebacks``): a card dropped in Done / Won't
   Do sets its Feedback-sheet row's Status to Complete / Won't Do; dragging
   it back out restores "Needs Review". Two modes:

   * **Webhook triage** (``store.webhook_triage`` on + URL configured — the
     preferred mode): POST a ``triage`` event per pending change to the
     telemetry flow; the flow matches ``row_key`` (``"{timestamp} {user}"``
     joined with ``|``) against the FeedbackTable's Key column and updates
     the Status cell SERVER-SIDE. The local workbook is never written, so
     the workbook has a single writer (the flow) and the OneDrive two-sided
     conflict class (silent multi-day sync wedges, seen 7/31 and 8/6/2026)
     is impossible by construction. The webhook 202s before the flow runs,
     so delivery is verified by READBACK: ``requeue_stale_writebacks`` re-
     queues any card whose row still reads "Needs Review" on a later
     refresh (idempotent re-send until the sheet agrees).
   * **Legacy local-file write** (flag off / no URL, e.g. offline dev):
     edits only the Status cell of existing rows — never row adds/moves/
     deletes — atomically via temp + os.replace. A drag-out restores
     "Needs Review" only when the cell still holds the value WE wrote (a
     manual edit in Excel always wins). A locked workbook just leaves the
     write-back pending for the next drop or Refresh.

   Both modes record ``written_status`` (the value last delivered) only
   after the write lands (file save / 2xx), keeping the flush idempotent
   and safe to retry.

Column lookups go by header NAME, never a fixed index (Hard Rule 1).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STATE_VERSION = 1

TODO_BUCKET_ID = "todo"
DONE_BUCKET_ID = "done"
WONT_DO_BUCKET_ID = "wont_do"

DEFAULT_BUCKETS = [
    {"id": TODO_BUCKET_ID, "name": "To-Do"},
    {"id": "in_progress", "name": "In Progress"},
    {"id": DONE_BUCKET_ID, "name": "Done"},
    {"id": WONT_DO_BUCKET_ID, "name": "Won't Do"},
]

# Status values written back to the Feedback sheet. Complete/Needs Review match
# the sheet's existing triage dropdown; add "Won't Do" to the dropdown list in
# Excel once so it isn't flagged by validation.
STATUS_COMPLETE = "Complete"
STATUS_WONT_DO = "Won't Do"
STATUS_NEEDS_REVIEW = "Needs Review"
WRITEBACK_STATUS_BY_BUCKET = {
    DONE_BUCKET_ID: STATUS_COMPLETE,
    WONT_DO_BUCKET_ID: STATUS_WONT_DO,
}


def _status_target_bucket(status: str) -> Optional[str]:
    """Bucket a Feedback-sheet Status value implies, or None for open/working
    statuses (Needs Review / Deferred / blank). Mirrors WRITEBACK_STATUS_BY_BUCKET
    in reverse so board <-> telemetry stay consistent."""
    s = (status or "").strip().lower()
    if s == STATUS_COMPLETE.lower():
        return DONE_BUCKET_ID
    if s == STATUS_WONT_DO.lower():
        return WONT_DO_BUCKET_ID
    return None

_WORKBOOK_NAME = "TechDeck Telemetry.xlsx"
_FEEDBACK_SHEET = "Feedback"
_ARCHIVE_SHEET = "Archive"

# How old the local workbook copy may get before the board calls it stale.
# Sized against the flow's write cadence (a usage row per run, every user), so
# well under a working day of legitimate silence.
STALE_AFTER_HOURS = 12


# ---------------------------------------------------------------------------
# Feedback source (read-only)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FeedbackEntry:
    """One row of the Feedback/Archive sheet, normalised."""
    key: str
    title: str            # the Suggestion text
    user: str
    date_iso: str         # ISO timestamp string ("" if unparseable)
    which_feature: str
    version: str
    orig_status: str
    source: str           # "feedback" | "archive"

    @property
    def sort_key(self) -> str:
        return self.date_iso or ""


def _card_key(date_iso: str, user: str, suggestion: str) -> str:
    raw = f"{date_iso}|{user}|{suggestion}".encode("utf-8", "replace")
    return hashlib.sha1(raw).hexdigest()[:12]


def _iso(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return ""
    return str(value).strip()


def telemetry_workbook_path() -> Optional[Path]:
    """Locate ``TechDeck Telemetry.xlsx`` in the maintainer's OneDrive.

    The OneDrive folder's exact name varies per machine, so we scan every
    ``OneDrive*`` folder under the home dir for ``TechDeck/TechDeck
    Telemetry.xlsx``. An explicit ``TECHDECK_TELEMETRY_XLSX`` env var overrides
    the search (handy when the workbook lives somewhere non-standard).
    """
    override = os.environ.get("TECHDECK_TELEMETRY_XLSX")
    if override:
        p = Path(override)
        return p if p.exists() else None
    home = Path.home()
    for onedrive in sorted(home.glob("OneDrive*")):
        candidate = onedrive / "TechDeck" / _WORKBOOK_NAME
        if candidate.exists():
            return candidate
    return None


def _read_sheet(wb, sheet_name: str, source: str) -> list[FeedbackEntry]:
    """Read one sheet into FeedbackEntry records, mapping columns by header
    name and skipping the header + any fully-blank spacer rows."""
    if sheet_name not in wb.sheetnames:
        return []
    ws = wb[sheet_name]
    rows = ws.iter_rows(values_only=True)

    # Find the header row (the first row carrying both Timestamp and Suggestion).
    header_map: dict[str, int] = {}
    for row in rows:
        cells = {str(c).strip().lower(): i for i, c in enumerate(row) if c is not None}
        if "timestamp" in cells and "suggestion" in cells:
            header_map = cells
            break
    if not header_map:
        return []

    def cell(row, name: str):
        idx = header_map.get(name)
        if idx is None or idx >= len(row):
            return None
        return row[idx]

    entries: list[FeedbackEntry] = []
    for row in rows:  # continues after the header row
        suggestion = cell(row, "suggestion")
        timestamp = cell(row, "timestamp")
        if not suggestion and not timestamp:
            continue  # spacer / blank row
        title = "" if suggestion is None else str(suggestion).strip()
        if not title:
            continue
        date_iso = _iso(timestamp)
        user = "" if cell(row, "user") is None else str(cell(row, "user")).strip()
        which = cell(row, "which feature")
        which_feature = "" if which is None else str(which).strip()
        version = cell(row, "techdeck version")
        version = "" if version is None else str(version).strip()
        status = cell(row, "status")
        orig_status = "" if status is None else str(status).strip()
        entries.append(FeedbackEntry(
            key=_card_key(date_iso, user, title),
            title=title, user=user, date_iso=date_iso,
            which_feature=which_feature, version=version,
            orig_status=orig_status, source=source,
        ))
    return entries


@dataclass
class FeedbackLoad:
    """Result of a load attempt: the rows, plus a human-readable status."""
    feedback: list[FeedbackEntry] = field(default_factory=list)
    archive: list[FeedbackEntry] = field(default_factory=list)
    path: Optional[Path] = None
    ok: bool = False
    message: str = ""
    mtime_iso: str = ""      # local copy's last-modified time ("" if unknown)

    @property
    def age_hours(self) -> Optional[float]:
        """Hours since the local copy last changed, or None if unknown."""
        if not self.mtime_iso:
            return None
        try:
            delta = datetime.now() - datetime.fromisoformat(self.mtime_iso)
        except ValueError:
            return None
        return delta.total_seconds() / 3600.0

    @property
    def is_stale(self) -> bool:
        """True when the local copy looks like it stopped syncing DOWN.

        The flow appends a usage row on every plugin run by every user — dozens
        a day — so the cloud copy changes constantly, and a local copy untouched
        for STALE_AFTER_HOURS means the DOWNLOAD side is wedged rather than that
        nothing happened. This is the signal that was missing when a silent
        OneDrive deadlock starved the board for six days: an empty board looked
        identical to "no new feedback" (docs/USAGE_TELEMETRY.md troubleshooting).
        """
        age = self.age_hours
        return age is not None and age >= STALE_AFTER_HOURS


def load_feedback() -> FeedbackLoad:
    """Read the Feedback + Archive sheets. Never raises — failures come back as
    ``ok=False`` with a message the board can show."""
    path = telemetry_workbook_path()
    if path is None:
        return FeedbackLoad(
            message="Telemetry workbook not found under any OneDrive folder "
                    "(looked for TechDeck/TechDeck Telemetry.xlsx). Set "
                    "TECHDECK_TELEMETRY_XLSX to point at it.")
    try:
        mtime_iso = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    except OSError:
        mtime_iso = ""
    try:
        from techdeck.core import plugin_sdk as sdk
        wb = sdk.load_workbook_resilient(path, read_only=True, data_only=True)
    except Exception as exc:  # locked / placeholder / corrupt — report, don't crash
        logger.warning("Dev Board: could not read %s: %s", path, exc)
        return FeedbackLoad(path=path, message=str(exc), mtime_iso=mtime_iso)
    try:
        feedback = _read_sheet(wb, _FEEDBACK_SHEET, "feedback")
        archive = _read_sheet(wb, _ARCHIVE_SHEET, "archive")
    finally:
        wb.close()
    return FeedbackLoad(
        feedback=feedback, archive=archive, path=path, ok=True,
        mtime_iso=mtime_iso,
        message=f"{len(feedback)} open + {len(archive)} archived from {path.name}")


# ---------------------------------------------------------------------------
# Write-back (Status cells only — never rows; see module docstring)
# ---------------------------------------------------------------------------

@dataclass
class WritebackResult:
    """Outcome of one flush attempt, for the board's status line."""
    attempted: int = 0    # pending items going in
    written: int = 0      # Status changes delivered (file cells / flow events)
    adopted: int = 0      # already-correct cells / manual edits left alone
    missing: int = 0      # rows no longer on the Feedback sheet (archived?)
    ok: bool = True       # False = nothing persisted; retry later
    message: str = ""
    via_webhook: bool = False   # True = sent as triage events, not file writes


def _locate_header(ws) -> tuple[Optional[int], dict[str, int]]:
    """Find the Feedback header row: (1-based row index, {header: 1-based col}).
    Scans by NAME (Hard Rules 1+2), capped to the top of the sheet — the header
    is row 1 in practice, never thousands of rows down."""
    for r, row in enumerate(ws.iter_rows(values_only=True), start=1):
        cells = {str(c).strip().lower(): i + 1
                 for i, c in enumerate(row) if c is not None}
        if "timestamp" in cells and "suggestion" in cells:
            return r, cells
        if r >= 50:
            break
    return None, {}


def _triage_webhook_available() -> bool:
    try:
        from techdeck.core.constants import TELEMETRY_WEBHOOK_URL
        return bool(TELEMETRY_WEBHOOK_URL)
    except Exception:
        return False


def flush_writebacks(store: "BoardStore") -> WritebackResult:
    """Deliver pending Status changes. Never raises.

    Dispatch: webhook triage when enabled + configured (the flow updates the
    cloud workbook server-side — single-writer, no local file write),
    otherwise the legacy local-file cell write. See the module docstring for
    the two modes' contracts.
    """
    if store.webhook_triage and _triage_webhook_available():
        return _flush_writebacks_webhook(store)
    return _flush_writebacks_file(store)


def _flush_writebacks_webhook(store: "BoardStore") -> WritebackResult:
    """POST pending Status changes as ``triage`` events to the telemetry
    flow. ``written_status`` is recorded on 2xx; actual landing is verified
    by readback on a later refresh (``requeue_stale_writebacks``), because
    the Teams-webhook trigger 202s before the flow run executes."""
    pending = store.pending_writebacks()
    res = WritebackResult(attempted=len(pending), via_webhook=True)
    if not pending:
        return res
    events: list[dict] = []
    landed: dict[str, str] = {}
    for key, desired in pending:
        card = store.cards.get(key)
        if card is None:
            continue
        ts = (card.get("date") or "").replace("T", " ")
        user = card.get("user") or ""
        events.append({
            "timestamp": ts,
            "user": user,
            "machine": os.environ.get("COMPUTERNAME") or "unknown",
            "techdeck_version": _app_version(),
            "row_key": f"{ts}|{user}",
            "new_status": desired,
        })
        landed[key] = "" if desired == STATUS_NEEDS_REVIEW else desired
    try:
        from techdeck.core import usage_tracker
        ok = usage_tracker.post_triage_events(events)
    except Exception as exc:
        logger.warning("Dev Board triage webhook failed: %s", exc)
        res.ok = False
        res.message = str(exc)
        return res
    if not ok:
        res.ok = False
        res.message = "triage webhook returned an error status"
        return res
    res.written = len(events)
    changed = False
    for key, new_written in landed.items():
        card = store.cards.get(key)
        if card is not None and (card.get("written_status") or "") != new_written:
            card["written_status"] = new_written
            changed = True
    if changed:
        store.save()
    return res


def _app_version() -> str:
    try:
        from techdeck.core.constants import APP_VERSION
        return APP_VERSION
    except Exception:
        return ""


def _flush_writebacks_file(store: "BoardStore") -> WritebackResult:
    """Write pending Status changes into the Feedback sheet. Never raises.

    Atomic + idempotent: the edited workbook is saved to a temp file and
    os.replace'd over the original, and each card's ``written_status`` is
    persisted only AFTER that replace lands — a locked/cloud-only workbook
    leaves everything pending for the next attempt. Rows that no longer exist
    on the sheet (edited, or manually cut to Archive) are adopted without a
    write so they don't stay pending forever.
    """
    pending = store.pending_writebacks()
    res = WritebackResult(attempted=len(pending))
    if not pending:
        return res
    path = telemetry_workbook_path()
    if path is None:
        res.ok = False
        res.message = "telemetry workbook not found"
        return res
    try:
        from techdeck.core import plugin_sdk as sdk
        wb = sdk.load_workbook_resilient(path)   # write mode
    except Exception as exc:
        logger.warning("Dev Board write-back: could not open %s: %s", path, exc)
        res.ok = False
        res.message = str(exc)
        return res

    dirty = False
    landed: dict[str, str] = {}   # card key -> new written_status ("" = clear)
    try:
        if _FEEDBACK_SHEET not in wb.sheetnames:
            res.ok = False
            res.message = f"no '{_FEEDBACK_SHEET}' sheet"
            return res
        ws = wb[_FEEDBACK_SHEET]
        header_row, cols = _locate_header(ws)
        status_col = cols.get("status")
        if header_row is None or status_col is None:
            res.ok = False
            res.message = "Feedback sheet has no Status column"
            return res

        # Index sheet rows by the same identity the cards use.
        row_by_key: dict[str, int] = {}
        for r in range(header_row + 1, ws.max_row + 1):
            def val(name):
                idx = cols.get(name)
                return None if idx is None else ws.cell(row=r, column=idx).value
            suggestion = val("suggestion")
            title = "" if suggestion is None else str(suggestion).strip()
            if not title:
                continue
            user = val("user")
            user = "" if user is None else str(user).strip()
            row_by_key[_card_key(_iso(val("timestamp")), user, title)] = r

        for key, desired in pending:
            card = store.cards.get(key)
            if card is None:
                continue
            r = row_by_key.get(key)
            if r is None:
                # Row edited or manually moved to Archive — adopt and move on.
                res.missing += 1
                landed[key] = "" if desired == STATUS_NEEDS_REVIEW else desired
                continue
            current = ws.cell(row=r, column=status_col).value
            current = "" if current is None else str(current).strip()
            written = card.get("written_status") or ""
            if desired == STATUS_NEEDS_REVIEW:
                # Restore only over OUR value; a manual edit in Excel wins.
                if current == written:
                    ws.cell(row=r, column=status_col).value = STATUS_NEEDS_REVIEW
                    dirty = True
                    res.written += 1
                else:
                    res.adopted += 1
                landed[key] = ""
            else:
                if current == desired:
                    res.adopted += 1     # already there (manual or earlier write)
                else:
                    ws.cell(row=r, column=status_col).value = desired
                    dirty = True
                    res.written += 1
                landed[key] = desired

        if dirty:
            tmp = path.with_name(path.stem + ".writeback.tmp.xlsx")
            wb.save(tmp)
            try:
                os.replace(tmp, path)
            except Exception as exc:
                try:
                    tmp.unlink()
                except OSError:
                    pass
                logger.warning("Dev Board write-back: could not replace %s: %s",
                               path, exc)
                res.ok = False
                res.written = 0
                res.message = ("workbook is open in Excel — close it and Refresh"
                               if isinstance(exc, PermissionError) else str(exc))
                return res
    finally:
        wb.close()

    # Only now — after the file write landed (or none was needed) — record what
    # we own, so a failed save retries cleanly next time.
    changed = False
    for key, new_written in landed.items():
        card = store.cards.get(key)
        if card is not None and (card.get("written_status") or "") != new_written:
            card["written_status"] = new_written
            changed = True
    if changed:
        store.save()
    return res


# ---------------------------------------------------------------------------
# Board state (persistent overlay)
# ---------------------------------------------------------------------------

def _state_path() -> Path:
    from techdeck.core.settings import SettingsManager
    base = SettingsManager().settings_dir / "devkit"
    base.mkdir(parents=True, exist_ok=True)
    return base / "todo_board.json"


class BoardStore:
    """The persistent board: an ordered list of buckets (each an ordered list of
    card keys) plus a per-card content dict. Every mutation saves atomically."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else _state_path()
        self.buckets: list[dict] = []   # [{id, name, cards: [key, ...]}]
        self.cards: dict[str, dict] = {}
        # Keys the user has "cleared" off the board (completed items acknowledged
        # and hidden). Remembered so the archived telemetry rows behind them
        # don't just re-sync back in; a row that later reopens resurrects.
        self.cleared: set[str] = set()
        self.settings: dict = {}        # board prefs (e.g. webhook_triage)
        self._load()

    # ---- persistence -----------------------------------------------------

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.buckets = data.get("buckets") or []
                self.cards = data.get("cards") or {}
                self.cleared = set(data.get("cleared") or [])
                self.settings = data.get("settings") or {}
            except Exception as exc:
                logger.warning("Dev Board: state unreadable (%s); starting fresh", exc)
                self.buckets, self.cards, self.cleared = [], {}, set()
                self.settings = {}
        if not self.buckets:
            self.buckets = [dict(b, cards=[]) for b in DEFAULT_BUCKETS]
        for b in self.buckets:
            b.setdefault("cards", [])
        self._reconcile()

    def save(self):
        payload = {"version": STATE_VERSION, "buckets": self.buckets,
                   "cards": self.cards, "cleared": sorted(self.cleared),
                   "settings": self.settings}
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    # ---- settings --------------------------------------------------------

    @property
    def webhook_triage(self) -> bool:
        """True = deliver Status write-backs as triage events through the
        telemetry flow (requires the flow's triage branch — see
        docs/USAGE_TELEMETRY.md). Default OFF: with the flag on but the flow
        branch missing, triage events would fall into the flow's feedback
        branch and append blank-suggestion junk rows."""
        return bool(self.settings.get("webhook_triage"))

    def set_webhook_triage(self, on: bool):
        self.settings["webhook_triage"] = bool(on)
        self.save()

    def _reconcile(self):
        """Repair drift: drop bucket refs to unknown cards, and file any card
        that isn't in a bucket into the first bucket. Guarantees every card
        appears in exactly one bucket."""
        seen: set[str] = set()
        for b in self.buckets:
            deduped = []
            for key in b["cards"]:
                if key in self.cards and key not in seen:
                    deduped.append(key)
                    seen.add(key)
            b["cards"] = deduped
        orphans = [k for k in self.cards if k not in seen]
        if orphans and self.buckets:
            self.buckets[0]["cards"].extend(orphans)

    # ---- lookups ---------------------------------------------------------

    def bucket(self, bucket_id: str) -> Optional[dict]:
        return next((b for b in self.buckets if b["id"] == bucket_id), None)

    def bucket_of(self, key: str) -> Optional[dict]:
        return next((b for b in self.buckets if key in b["cards"]), None)

    # ---- sync from telemetry --------------------------------------------

    def _new_card(self, e: FeedbackEntry) -> dict:
        return {
            "title": e.title, "user": e.user, "date": e.date_iso,
            "which_feature": e.which_feature, "version": e.version,
            "orig_status": e.orig_status, "source": e.source,
            "labels": [e.which_feature] if e.which_feature else [],
            "checklist": [], "dismissed": False,
            "written_status": "",   # last Status value WE wrote to the sheet
        }

    def sync(self, load: FeedbackLoad) -> int:
        """Fold new feedback rows into the board. Live rows land at the top of
        To-Do (newest first); archived rows go to Done. Existing cards keep
        wherever the user dragged them. Returns how many cards were added."""
        if not load.ok:
            return 0
        todo = self.bucket(TODO_BUCKET_ID) or (self.buckets[0] if self.buckets else None)
        done = self.bucket(DONE_BUCKET_ID) or (self.buckets[-1] if self.buckets else None)
        added = 0
        for e in sorted(load.feedback, key=lambda x: x.sort_key):
            if e.key in self.cards:
                continue
            if e.key in self.cleared:
                # Cleared earlier. Resurrect only if it's genuinely open again
                # (reopened) — a still-terminal row stays cleared.
                if _status_target_bucket(e.orig_status) is not None:
                    continue
                self.cleared.discard(e.key)
            self.cards[e.key] = self._new_card(e)
            if todo is not None:
                todo["cards"].insert(0, e.key)  # oldest first -> newest ends on top
            added += 1
        for e in sorted(load.archive, key=lambda x: x.sort_key):
            if e.key in self.cards or e.key in self.cleared:
                continue  # cleared archived rows stay off the board
            self.cards[e.key] = self._new_card(e)
            if done is not None:
                done["cards"].append(e.key)
            added += 1
        if added:
            self.save()
        return added

    def clear_bucket(self, bucket_id: str) -> int:
        """Remove every card in ``bucket_id`` from the board and remember the keys.

        Meant for the terminal buckets (Done / Won't Do): the telemetry rows stay
        on the Archive sheet — the record of record — so nothing is truly lost;
        this just clears the pile off the board. Remembered keys keep the
        archived rows from re-syncing, but a row that later reopens (returns to an
        open status) still comes back via ``sync``. Returns the count removed.
        """
        b = self.bucket(bucket_id)
        if b is None or not b["cards"]:
            return 0
        keys = list(b["cards"])
        for key in keys:
            self.cards.pop(key, None)
            self.cleared.add(key)
        b["cards"] = []
        self.save()
        return len(keys)

    def apply_external_status(self, load: "FeedbackLoad") -> int:
        """Reflect completion that happened OUTSIDE the board — a maintainer
        marked a Feedback row Complete/Won't Do, or the row was archived — by
        moving the matching card into Done / Won't Do. This is what makes
        "mark these tasks complete" (done in the workbook, not by dragging)
        actually move the cards.

        Rules that keep it from fighting the user:
          * Only cards still in a WORKING bucket advance; a card already parked
            in a terminal bucket (Done / Won't Do) is left where the user put it,
            and nothing is ever pulled back OUT of a terminal bucket.
          * Only telemetry-backed cards (source == "feedback") react; manual
            cards are untouched.
          * The applied status is recorded as ``written_status`` so the
            write-back treats it as already in sync (no redundant rewrite), while
            a later drag OUT still correctly restores "Needs Review".

        Returns the number of cards moved.
        """
        if not load.ok:
            return 0
        target_by_key: dict[str, str] = {}
        for e in load.feedback:
            bucket_id = _status_target_bucket(e.orig_status)
            if bucket_id is not None:
                target_by_key[e.key] = bucket_id
        for e in load.archive:
            target_by_key[e.key] = DONE_BUCKET_ID   # archived == complete

        moved = 0
        for key, target in target_by_key.items():
            card = self.cards.get(key)
            if card is None or card.get("source") != "feedback":
                continue
            cur = self.bucket_of(key)
            if cur is None or cur["id"] == target:
                continue
            if cur["id"] in (DONE_BUCKET_ID, WONT_DO_BUCKET_ID):
                continue   # respect the terminal bucket the user chose
            if card.get("written_status"):
                # A "Needs Review" restore is still in flight for this card
                # (dragged out of a terminal bucket; webhook/sheet lag hasn't
                # caught up). The row's terminal status is OUR stale value —
                # honoring it would yank the card straight back.
                continue
            dst = self.bucket(target)
            if dst is None:
                continue
            cur["cards"].remove(key)
            dst["cards"].append(key)
            card["written_status"] = WRITEBACK_STATUS_BY_BUCKET.get(target, "")
            moved += 1
        if moved:
            self.save()
        return moved

    # ---- write-back ------------------------------------------------------

    def requeue_stale_writebacks(self, load: "FeedbackLoad") -> int:
        """Readback verification: re-queue terminal write-backs that never
        landed. A card whose ``written_status`` says we delivered Complete /
        Won't Do, but whose Feedback row still reads "Needs Review", had its
        delivery lost — a failed flow run behind the webhook's 202, or (file
        mode) the workbook reverted under us (OneDrive conflict resolution).
        Clearing ``written_status`` puts it back in ``pending_writebacks``;
        the re-send is idempotent so convergence is safe to retry.

        Deliberately narrow: only an exact "Needs Review" re-queues. Any
        other value (Deferred, free text) is a manual edit and wins — to
        reopen a Done-carded row by hand, drag the card out of Done instead
        of editing the cell. Returns how many were re-queued.
        """
        if not load.ok:
            return 0
        status_by_key = {e.key: (e.orig_status or "").strip()
                         for e in load.feedback}
        requeued = 0
        for key, card in self.cards.items():
            written = card.get("written_status") or ""
            if written not in (STATUS_COMPLETE, STATUS_WONT_DO):
                continue
            if status_by_key.get(key) == STATUS_NEEDS_REVIEW:
                card["written_status"] = ""
                requeued += 1
        if requeued:
            self.save()
        return requeued

    def pending_writebacks(self) -> list[tuple[str, str]]:
        """Cards whose Feedback-sheet Status should change, as
        ``[(card_key, desired_status)]``.

        - In a terminal bucket (Done / Won't Do) and we haven't recorded a
          successful write of that value yet -> write the mapped status.
        - NOT in a terminal bucket but ``written_status`` says we previously
          wrote one -> restore ``Needs Review`` (the flush only actually writes
          it if the cell still holds our value — manual edits win).

        Only telemetry-backed live rows participate: manual cards have no row,
        and archive-sourced cards live on the Archive sheet we never write.
        """
        out: list[tuple[str, str]] = []
        for b in self.buckets:
            target = WRITEBACK_STATUS_BY_BUCKET.get(b["id"])
            for key in b["cards"]:
                card = self.cards.get(key)
                if card is None or card.get("source") != "feedback":
                    continue
                written = card.get("written_status") or ""
                if target is not None:
                    if written != target:
                        out.append((key, target))
                elif written:
                    out.append((key, STATUS_NEEDS_REVIEW))
        return out

    # ---- card mutations --------------------------------------------------

    def move_card(self, key: str, to_bucket_id: str, index: int):
        """Move ``key`` to ``to_bucket_id`` at ``index``. ``index`` is the target
        position among the destination's OTHER cards (the drag source is hidden
        while dropping, so the UI already computes it against the list with this
        card removed) — hence no same-bucket shift adjustment here."""
        src = self.bucket_of(key)
        dst = self.bucket(to_bucket_id)
        if dst is None or key not in self.cards:
            return
        if src is not None:
            src["cards"].remove(key)
        index = max(0, min(index, len(dst["cards"])))
        dst["cards"].insert(index, key)
        self.save()

    def add_manual_card(self, bucket_id: str, title: str) -> str:
        key = "m_" + uuid.uuid4().hex[:10]
        self.cards[key] = {
            "title": title.strip() or "New task", "user": "", "date": "",
            "which_feature": "", "version": "", "orig_status": "",
            "source": "manual", "labels": [], "checklist": [], "dismissed": False,
        }
        b = self.bucket(bucket_id) or (self.buckets[0] if self.buckets else None)
        if b is not None:
            b["cards"].insert(0, key)
        self.save()
        return key

    def delete_card(self, key: str):
        b = self.bucket_of(key)
        if b is not None:
            b["cards"].remove(key)
        self.cards.pop(key, None)
        self.save()

    def set_title(self, key: str, title: str):
        if key in self.cards:
            self.cards[key]["title"] = title.strip()
            self.save()

    def set_done(self, key: str, done: bool):
        """Card-level completion (the Teams-style collapse). Independent of
        which bucket the card sits in — it only drives the card's rendering."""
        if key in self.cards:
            self.cards[key]["done"] = bool(done)
            self.save()

    # ---- labels ----------------------------------------------------------

    def add_label(self, key: str, label: str):
        label = label.strip()
        if not label or key not in self.cards:
            return
        labels = self.cards[key].setdefault("labels", [])
        if label not in labels:
            labels.append(label)
            self.save()

    def remove_label(self, key: str, label: str):
        if key in self.cards and label in self.cards[key].get("labels", []):
            self.cards[key]["labels"].remove(label)
            self.save()

    # ---- checklist -------------------------------------------------------

    def add_checklist_item(self, key: str, text: str):
        text = text.strip()
        if not text or key not in self.cards:
            return
        self.cards[key].setdefault("checklist", []).append({"text": text, "done": False})
        self.save()

    def toggle_checklist_item(self, key: str, index: int):
        items = self.cards.get(key, {}).get("checklist", [])
        if 0 <= index < len(items):
            items[index]["done"] = not items[index].get("done", False)
            self.save()

    def remove_checklist_item(self, key: str, index: int):
        items = self.cards.get(key, {}).get("checklist", [])
        if 0 <= index < len(items):
            items.pop(index)
            self.save()

    # ---- buckets ---------------------------------------------------------

    def add_bucket(self, name: str) -> str:
        bucket_id = "b_" + uuid.uuid4().hex[:8]
        self.buckets.append({"id": bucket_id, "name": name.strip() or "New bucket", "cards": []})
        self.save()
        return bucket_id

    def rename_bucket(self, bucket_id: str, name: str):
        b = self.bucket(bucket_id)
        if b is not None and name.strip():
            b["name"] = name.strip()
            self.save()

    def remove_bucket(self, bucket_id: str):
        """Delete a bucket; its cards fall back into the first remaining bucket
        (never lost)."""
        if len(self.buckets) <= 1:
            return
        b = self.bucket(bucket_id)
        if b is None:
            return
        self.buckets.remove(b)
        if b["cards"]:
            self.buckets[0]["cards"].extend(b["cards"])
        self.save()

    def move_bucket(self, bucket_id: str, new_index: int):
        b = self.bucket(bucket_id)
        if b is None:
            return
        self.buckets.remove(b)
        new_index = max(0, min(new_index, len(self.buckets)))
        self.buckets.insert(new_index, b)
        self.save()
