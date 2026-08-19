"""Assistant persistence.

Everything the Assistant page remembers lives in
``%LOCALAPPDATA%\\TechDeck\\assistant\\``:

    assistant.json   notes + tasks + schedules + prefs (one atomic document)
    chat.jsonl       the terminal transcript, append-only and capped

Two files rather than one because they have opposite access patterns: the
document is small and fully rewritten on every edit, while the transcript grows
by one line per message and is only ever appended to or tailed. Writing the
whole transcript back on every keystroke would be the slowest thing on the page.

Writes are atomic (temp file + ``os.replace``), matching SettingsManager, a
crash mid-write must never cost the user their notes.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from techdeck.core.assistant.models import (
    ChatMessage, Note, TaskItem, Schedule, SchedulePrefs, now_iso,
)
from techdeck.core.assistant.notifier import NotifyPrefs, prune_sent

# Keep the transcript bounded. Old lines are dropped from the FRONT on rotate,
# so history reads oldest→newest and the file can't grow without limit.
MAX_CHAT_LINES = 4000
CHAT_ROTATE_TO = 3000
# Generated schedules kept per user. Older ones fall off the end.
MAX_SCHEDULES = 40

# Transcript generation. Bumping this discards the existing chat.jsonl ONCE on
# the next launch. See _migrate for when that is and isn't justified.
CHAT_SCHEMA = 1


class AssistantStore:
    """Load/save the Assistant's data. Single-threaded (GUI thread) by design, every caller is a Qt slot."""

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            if os.name == "nt":
                root = Path(os.environ.get("LOCALAPPDATA", Path.home()))
            else:
                root = Path.home() / ".local" / "share"
            base_dir = root / "TechDeck" / "assistant"
        self.dir = Path(base_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.doc_path = self.dir / "assistant.json"
        self.chat_path = self.dir / "chat.jsonl"

        self.notes: List[Note] = []
        self.tasks: List[TaskItem] = []
        self.schedules: List[Schedule] = []
        self.prefs = SchedulePrefs()
        self.notify = NotifyPrefs()
        self.meta: Dict[str, Any] = {}

        self.load()

    # ── document ─────────────────────────────────────────────────────────────

    def load(self) -> None:
        data: Dict[str, Any] = {}
        if self.doc_path.exists():
            try:
                with open(self.doc_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError, OSError) as exc:
                # Never let a bad file take the page down, quarantine it so the
                # user can recover by hand, and carry on with an empty desk.
                logger.error("Could not read %s: %s - quarantining",
                             self.doc_path, exc)
                self._quarantine(self.doc_path)
                data = {}
        self.notes = [Note.from_dict(d) for d in data.get("notes", []) or []]
        self.tasks = [TaskItem.from_dict(d) for d in data.get("tasks", []) or []]
        self.schedules = [Schedule.from_dict(d) for d in data.get("schedules", []) or []]
        self.prefs = SchedulePrefs.from_dict(data.get("prefs", {}) or {})
        self.notify = NotifyPrefs.from_dict(data.get("notify", {}) or {})
        self.meta = dict(data.get("meta", {}) or {})
        self._migrate()

    def _migrate(self) -> None:
        """One-shot cleanups, keyed off a stamp in ``meta`` so each runs once.

        **Generation 1 discards the whole transcript.** The pre-release build
        opened with a greeting explaining that anything you typed became a
        task, and then auto-captured every line to prove it. Both behaviours
        were removed, but a transcript is a LOG: those lines stayed pinned at
        the top of the terminal, describing something the page no longer does,
        on every machine that had ever run the old build. Telling each person
        to type /clear is not a fix.

        Wiping a transcript is only defensible because of what it is: a scratch
        conversation, explicitly advertised as not stored work. Notes, tasks,
        schedules and preferences are never touched by a migration.
        """
        if int(self.meta.get("chat_schema", 0) or 0) >= CHAT_SCHEMA:
            return
        if self.chat_path.exists():
            self.clear_chat()
        self.meta["chat_schema"] = CHAT_SCHEMA
        self.save()

    def save(self) -> None:
        payload = {
            "version": 1,
            "saved_at": now_iso(),
            "prefs": self.prefs.to_dict(),
            "notify": self.notify.to_dict(),
            "notes": [n.to_dict() for n in self.notes],
            "tasks": [t.to_dict() for t in self.tasks],
            "schedules": [s.to_dict() for s in self.schedules[:MAX_SCHEDULES]],
            "meta": self.meta,
        }
        self._atomic_write_json(self.doc_path, payload)

    def _quarantine(self, path: Path) -> None:
        try:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path.replace(path.with_suffix(f".corrupt_{stamp}.json"))
        except OSError:
            pass

    def _atomic_write_json(self, path: Path, payload: Any) -> None:
        tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    # ── notes ────────────────────────────────────────────────────────────────

    def add_note(self, note: Note) -> Note:
        self.notes.insert(0, note)
        self.save()
        return note

    def update_note(self, note: Note) -> None:
        note.updated_at = now_iso()
        for i, existing in enumerate(self.notes):
            if existing.id == note.id:
                self.notes[i] = note
                break
        else:
            self.notes.insert(0, note)
        self.save()

    def delete_note(self, note_id: str) -> bool:
        before = len(self.notes)
        self.notes = [n for n in self.notes if n.id != note_id]
        if len(self.notes) != before:
            self.save()
            return True
        return False

    def get_note(self, note_id: str) -> Optional[Note]:
        return next((n for n in self.notes if n.id == note_id), None)

    def sorted_notes(self) -> List[Note]:
        """Pinned first, then most recently touched. Two passes rather than one
        clever key, ISO timestamps sort lexically, so a plain reverse sort on
        updated_at is exact, and the stable sort then floats the pins."""
        by_recency = sorted(self.notes, key=lambda n: n.updated_at, reverse=True)
        return sorted(by_recency, key=lambda n: 0 if n.pinned else 1)

    # ── tasks ────────────────────────────────────────────────────────────────

    def add_task(self, task: TaskItem) -> TaskItem:
        self.tasks.append(task)
        self.save()
        return task

    def update_task(self, task: TaskItem) -> None:
        task.updated_at = now_iso()
        for i, existing in enumerate(self.tasks):
            if existing.id == task.id:
                self.tasks[i] = task
                break
        else:
            self.tasks.append(task)
        self.save()

    def delete_task(self, task_id: str) -> bool:
        before = len(self.tasks)
        self.tasks = [t for t in self.tasks if t.id != task_id]
        if len(self.tasks) != before:
            self.save()
            return True
        return False

    def get_task(self, task_id: str) -> Optional[TaskItem]:
        return next((t for t in self.tasks if t.id == task_id), None)

    def open_tasks(self) -> List[TaskItem]:
        return [t for t in self.tasks if not t.done]

    def set_done(self, task_id: str, done: bool = True) -> Optional[TaskItem]:
        task = self.get_task(task_id)
        if task is None:
            return None
        task.done = done
        task.done_at = now_iso() if done else None
        self.update_task(task)
        return task

    def find_tasks(self, needle: str, include_done: bool = False) -> List[TaskItem]:
        """Substring match on the title, case-insensitive. Used by `/done fix po`
        so the user never has to type an id."""
        needle = (needle or "").strip().lower()
        if not needle:
            return []
        pool = self.tasks if include_done else self.open_tasks()
        exact = [t for t in pool if t.title.strip().lower() == needle]
        if exact:
            return exact
        return [t for t in pool if needle in t.title.lower()]

    def purge_done(self, keep_days: int = 0) -> int:
        """Drop completed tasks older than ``keep_days``. Returns how many went."""
        cutoff = date.today().toordinal() - max(0, keep_days)
        kept, removed = [], 0
        for t in self.tasks:
            if not t.done:
                kept.append(t)
                continue
            stamp = t.done_at or t.updated_at
            try:
                when = datetime.fromisoformat(stamp).date().toordinal()
            except (ValueError, TypeError):
                when = cutoff  # unparseable → treat as recent, keep it
            if when < cutoff:
                removed += 1
            else:
                kept.append(t)
        if removed:
            self.tasks = kept
            self.save()
        return removed

    # ── schedules ────────────────────────────────────────────────────────────

    def add_schedule(self, schedule: Schedule) -> Schedule:
        self.schedules.insert(0, schedule)
        del self.schedules[MAX_SCHEDULES:]
        self.save()
        return schedule

    def latest_schedule(self) -> Optional[Schedule]:
        return self.schedules[0] if self.schedules else None

    def get_schedule(self, schedule_id: str) -> Optional[Schedule]:
        return next((s for s in self.schedules if s.id == schedule_id), None)

    def delete_schedule(self, schedule_id: str) -> bool:
        before = len(self.schedules)
        self.schedules = [s for s in self.schedules if s.id != schedule_id]
        if len(self.schedules) != before:
            self.save()
            return True
        return False

    # ── prefs ────────────────────────────────────────────────────────────────

    def save_prefs(self, prefs: SchedulePrefs) -> None:
        self.prefs = prefs
        self.save()

    def save_notify_prefs(self, notify: NotifyPrefs) -> None:
        self.notify = notify
        self.save()

    # ── sent reminders ───────────────────────────────────────────────────────

    def sent_reminders(self) -> List[str]:
        """Keys of reminders already shown. Persisted so restarting TechDeck
        does not replay the morning."""
        return list(self.meta.get("sent_reminders", []) or [])

    def mark_reminders_sent(self, keys: List[str]) -> None:
        if not keys:
            return
        self.meta["sent_reminders"] = prune_sent(self.sent_reminders() + keys)
        self.save()

    # ── chat transcript ──────────────────────────────────────────────────────

    def append_chat(self, message: ChatMessage) -> None:
        """Append one transcript line. Best-effort: a failed write costs the
        history of one line, never the message the user is looking at."""
        try:
            with open(self.chat_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(message.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Chat append failed: %s", exc)
            return
        self._maybe_rotate_chat()

    def load_chat(self, limit: int = 400) -> List[ChatMessage]:
        """The last ``limit`` transcript lines, oldest first."""
        if not self.chat_path.exists():
            return []
        try:
            with open(self.chat_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return []
        out: List[ChatMessage] = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(ChatMessage.from_dict(json.loads(line)))
            except json.JSONDecodeError:
                continue        # skip a torn line, keep the rest of the history
        return out

    def clear_chat(self) -> None:
        try:
            self.chat_path.write_text("", encoding="utf-8")
        except OSError:
            pass

    def _maybe_rotate_chat(self) -> None:
        try:
            if self.chat_path.stat().st_size < 512_000:
                return          # cheap guard: only count lines on a big file
            with open(self.chat_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) <= MAX_CHAT_LINES:
                return
            keep = lines[-CHAT_ROTATE_TO:]
            tmp = self.chat_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                f.writelines(keep)
            os.replace(tmp, self.chat_path)
        except OSError as exc:
            logger.warning("Chat rotate failed: %s", exc)
