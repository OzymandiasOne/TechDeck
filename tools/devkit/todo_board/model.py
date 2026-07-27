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

DEFAULT_BUCKETS = [
    {"id": TODO_BUCKET_ID, "name": "To-Do"},
    {"id": "in_progress", "name": "In Progress"},
    {"id": DONE_BUCKET_ID, "name": "Done"},
    {"id": "wont_do", "name": "Won't Do"},
]

_WORKBOOK_NAME = "TechDeck Telemetry.xlsx"
_FEEDBACK_SHEET = "Feedback"
_ARCHIVE_SHEET = "Archive"


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
        from techdeck.core import plugin_sdk as sdk
        wb = sdk.load_workbook_resilient(path, read_only=True, data_only=True)
    except Exception as exc:  # locked / placeholder / corrupt — report, don't crash
        logger.warning("Dev Board: could not read %s: %s", path, exc)
        return FeedbackLoad(path=path, message=str(exc))
    try:
        feedback = _read_sheet(wb, _FEEDBACK_SHEET, "feedback")
        archive = _read_sheet(wb, _ARCHIVE_SHEET, "archive")
    finally:
        wb.close()
    return FeedbackLoad(
        feedback=feedback, archive=archive, path=path, ok=True,
        message=f"{len(feedback)} open + {len(archive)} archived from {path.name}")


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
        self._load()

    # ---- persistence -----------------------------------------------------

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.buckets = data.get("buckets") or []
                self.cards = data.get("cards") or {}
            except Exception as exc:
                logger.warning("Dev Board: state unreadable (%s); starting fresh", exc)
                self.buckets, self.cards = [], {}
        if not self.buckets:
            self.buckets = [dict(b, cards=[]) for b in DEFAULT_BUCKETS]
        for b in self.buckets:
            b.setdefault("cards", [])
        self._reconcile()

    def save(self):
        payload = {"version": STATE_VERSION, "buckets": self.buckets, "cards": self.cards}
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

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
            self.cards[e.key] = self._new_card(e)
            if todo is not None:
                todo["cards"].insert(0, e.key)  # oldest first -> newest ends on top
            added += 1
        for e in sorted(load.archive, key=lambda x: x.sort_key):
            if e.key in self.cards:
                continue
            self.cards[e.key] = self._new_card(e)
            if done is not None:
                done["cards"].append(e.key)
            added += 1
        if added:
            self.save()
        return added

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
