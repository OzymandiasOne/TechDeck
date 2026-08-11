"""Assistant data model — plain dataclasses, JSON round-trippable.

Every model carries ``to_dict`` / ``from_dict`` so the store can persist them
without a serializer library, and so an older settings file that predates a
field still loads (every ``from_dict`` uses ``.get`` with the default).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, time, timedelta
from typing import Any, Dict, List, Optional


# ── Priority ─────────────────────────────────────────────────────────────────
# Ordered most→least important. The weight is the "cost of delay" numerator in
# the scheduler's WSJF score, so the gaps matter: a critical task is worth ~3
# mediums, and a low task only earns time once everything else is placed.
PRIORITIES = ["critical", "high", "medium", "low"]
PRIORITY_LABELS = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}
PRIORITY_WEIGHT = {"critical": 10.0, "high": 6.0, "medium": 3.0, "low": 1.0}


def new_id(prefix: str = "") -> str:
    """Short, collision-safe id. Prefixed so a stray id in a log is readable."""
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Tolerant ISO parse. Accepts a bare date ('2026-08-12' → midnight) and
    returns None for anything unparseable rather than raising — a hand-edited
    JSON file must never take the page down."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _parse_date(value: Optional[str]) -> Optional[date]:
    dt = _parse_dt(value)
    return dt.date() if dt else None


# ── Chat ─────────────────────────────────────────────────────────────────────

@dataclass
class ChatMessage:
    """One line of terminal transcript. Persisted to chat.jsonl so history
    survives across sessions."""
    role: str                 # 'user' | 'deck' | 'system' | 'error' | 'result'
    text: str
    ts: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {"role": self.role, "text": self.text, "ts": self.ts}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ChatMessage":
        return cls(role=d.get("role", "system"), text=d.get("text", ""),
                   ts=d.get("ts", now_iso()))


# ── Notes ────────────────────────────────────────────────────────────────────

@dataclass
class Note:
    """A free-form note. ``body`` is plain text with leading-space indentation
    for nested bullets — deliberately NOT rich text, so a note stays greppable,
    diff-able, and exportable as-is."""
    id: str = field(default_factory=lambda: new_id("n_"))
    title: str = "Untitled note"
    body: str = ""
    pinned: bool = False
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Note":
        return cls(
            id=d.get("id") or new_id("n_"),
            title=d.get("title", "Untitled note"),
            body=d.get("body", ""),
            pinned=bool(d.get("pinned", False)),
            tags=list(d.get("tags", []) or []),
            created_at=d.get("created_at", now_iso()),
            updated_at=d.get("updated_at", now_iso()),
        )

    def preview(self, limit: int = 80) -> str:
        """First non-empty body line, for the notes list."""
        for line in self.body.splitlines():
            stripped = line.strip().lstrip("-*• ").strip()
            if stripped:
                return stripped[:limit]
        return ""


# ── Tasks ────────────────────────────────────────────────────────────────────

@dataclass
class TaskItem:
    """One thing to do.

    ``fixed_start`` marks an appointment: it is placed at exactly that time and
    never moved, and the scheduler works around it. Everything else is
    flexible and gets packed by the engine.
    """
    id: str = field(default_factory=lambda: new_id("t_"))
    title: str = ""
    notes: str = ""
    links: List[str] = field(default_factory=list)
    priority: str = "medium"
    estimate_min: int = 30
    deadline: Optional[str] = None       # ISO date or datetime — "due by"
    fixed_start: Optional[str] = None    # ISO datetime — an immovable appointment
    splittable: bool = True              # may be sliced across several blocks
    done: bool = False
    done_at: Optional[str] = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    schedule_id: Optional[str] = None    # last schedule that placed it

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TaskItem":
        priority = str(d.get("priority", "medium")).lower()
        if priority not in PRIORITY_WEIGHT:
            priority = "medium"
        try:
            estimate = max(5, int(d.get("estimate_min", 30) or 30))
        except (TypeError, ValueError):
            estimate = 30
        return cls(
            id=d.get("id") or new_id("t_"),
            title=d.get("title", ""),
            notes=d.get("notes", ""),
            links=list(d.get("links", []) or []),
            priority=priority,
            estimate_min=estimate,
            deadline=d.get("deadline"),
            fixed_start=d.get("fixed_start"),
            splittable=bool(d.get("splittable", True)),
            done=bool(d.get("done", False)),
            done_at=d.get("done_at"),
            created_at=d.get("created_at", now_iso()),
            updated_at=d.get("updated_at", now_iso()),
            schedule_id=d.get("schedule_id"),
        )

    # -- derived helpers used by the scheduler + the UI -----------------------

    @property
    def weight(self) -> float:
        return PRIORITY_WEIGHT.get(self.priority, 3.0)

    def deadline_date(self) -> Optional[date]:
        return _parse_date(self.deadline)

    def fixed_datetime(self) -> Optional[datetime]:
        return _parse_dt(self.fixed_start)

    def urgency_multiplier(self, today: date) -> float:
        """How much the deadline inflates this task's cost of delay. Overdue and
        due-today are the same emergency; after a week a deadline stops
        influencing the order at all."""
        due = self.deadline_date()
        if due is None:
            return 1.0
        days = (due - today).days
        if days <= 0:
            return 3.0
        if days == 1:
            return 2.0
        if days <= 3:
            return 1.5
        if days <= 7:
            return 1.2
        return 1.0

    def score(self, today: date) -> float:
        """WSJF — cost of delay per minute of work. Ranks a 15-minute high
        against a 3-hour critical honestly instead of always running the
        loudest task first."""
        return (self.weight * self.urgency_multiplier(today)) / max(5, self.estimate_min)

    def label(self) -> str:
        return self.title.strip() or "(untitled task)"


# ── Schedule ─────────────────────────────────────────────────────────────────

BLOCK_TASK = "task"
BLOCK_BREAK = "break"
BLOCK_LUNCH = "lunch"
BLOCK_FIXED = "fixed"


@dataclass
class ScheduleBlock:
    """One row on the agenda. ``start``/``end`` are ISO datetimes."""
    start: str
    end: str
    kind: str = BLOCK_TASK
    title: str = ""
    task_id: Optional[str] = None
    note: str = ""
    part: int = 0                # 1-based chunk index when a task was split
    part_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScheduleBlock":
        return cls(
            start=d.get("start", ""), end=d.get("end", ""),
            kind=d.get("kind", BLOCK_TASK), title=d.get("title", ""),
            task_id=d.get("task_id"), note=d.get("note", ""),
            part=int(d.get("part", 0) or 0),
            part_count=int(d.get("part_count", 0) or 0),
        )

    def start_dt(self) -> Optional[datetime]:
        return _parse_dt(self.start)

    def end_dt(self) -> Optional[datetime]:
        return _parse_dt(self.end)

    def minutes(self) -> int:
        s, e = self.start_dt(), self.end_dt()
        return int((e - s).total_seconds() // 60) if s and e else 0

    def time_range(self) -> str:
        s, e = self.start_dt(), self.end_dt()
        if not s or not e:
            return ""
        return f"{fmt_time(s)}–{fmt_time(e)}"


@dataclass
class DaySchedule:
    day: str                                  # ISO date
    blocks: List[ScheduleBlock] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"day": self.day, "blocks": [b.to_dict() for b in self.blocks]}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DaySchedule":
        return cls(day=d.get("day", ""),
                   blocks=[ScheduleBlock.from_dict(b) for b in d.get("blocks", [])])

    def date_obj(self) -> Optional[date]:
        return _parse_date(self.day)

    def work_minutes(self) -> int:
        return sum(b.minutes() for b in self.blocks if b.kind in (BLOCK_TASK, BLOCK_FIXED))


@dataclass
class Schedule:
    """A generated plan. Kept whole (rather than recomputed on demand) so the
    user can look back at what they planned even after the tasks change."""
    id: str = field(default_factory=lambda: new_id("s_"))
    created_at: str = field(default_factory=now_iso)
    range_label: str = ""
    days: List[DaySchedule] = field(default_factory=list)
    unscheduled: List[Dict[str, Any]] = field(default_factory=list)  # {task_id,title,reason}
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "created_at": self.created_at,
            "range_label": self.range_label,
            "days": [d.to_dict() for d in self.days],
            "unscheduled": self.unscheduled,
            "warnings": self.warnings,
            "stats": self.stats,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Schedule":
        return cls(
            id=d.get("id") or new_id("s_"),
            created_at=d.get("created_at", now_iso()),
            range_label=d.get("range_label", ""),
            days=[DaySchedule.from_dict(x) for x in d.get("days", [])],
            unscheduled=list(d.get("unscheduled", []) or []),
            warnings=list(d.get("warnings", []) or []),
            stats=dict(d.get("stats", {}) or {}),
        )

    def all_blocks(self) -> List[ScheduleBlock]:
        return [b for day in self.days for b in day.blocks]

    def task_blocks(self) -> List[ScheduleBlock]:
        return [b for b in self.all_blocks() if b.kind in (BLOCK_TASK, BLOCK_FIXED)]


# ── Preferences ──────────────────────────────────────────────────────────────

@dataclass
class SchedulePrefs:
    """The shape of the user's working day. Persisted once and reused, so the
    wizard only has to ask about it when someone opens Advanced."""
    day_start: str = "07:00"
    day_end: str = "15:30"
    lunch_start: str = "11:30"
    lunch_minutes: int = 30
    include_weekends: bool = False
    # After this much unbroken work the engine drops in a breather. Set
    # focus_block_min to 0 to switch breathers off entirely.
    focus_block_min: int = 90
    breather_min: int = 10
    # Smallest slice a splittable task may be cut into — below this, context
    # switching costs more than the slot is worth.
    min_chunk_min: int = 25
    # Every estimate is padded by this much. People under-estimate; a plan
    # built on raw estimates is a plan that fails by 10am.
    buffer_pct: int = 15

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SchedulePrefs":
        base = cls()
        if not isinstance(d, dict):
            return base
        for key in base.to_dict():
            if key in d and d[key] is not None:
                setattr(base, key, d[key])
        # Clamp anything a hand-edited file could put out of range.
        base.lunch_minutes = max(0, min(180, int(base.lunch_minutes)))
        base.focus_block_min = max(0, min(480, int(base.focus_block_min)))
        base.breather_min = max(0, min(60, int(base.breather_min)))
        base.min_chunk_min = max(5, min(240, int(base.min_chunk_min)))
        base.buffer_pct = max(0, min(100, int(base.buffer_pct)))
        base.include_weekends = bool(base.include_weekends)
        return base

    def start_time(self) -> time:
        return parse_hhmm(self.day_start, time(7, 0))

    def end_time(self) -> time:
        return parse_hhmm(self.day_end, time(15, 30))

    def lunch_time(self) -> Optional[time]:
        if self.lunch_minutes <= 0:
            return None
        return parse_hhmm(self.lunch_start, time(11, 30))


# ── Small shared time helpers ────────────────────────────────────────────────

def parse_hhmm(value: str, default: time) -> time:
    """'7:00' / '07:00' / '15:30' → time. Anything else → default."""
    try:
        parts = str(value).strip().split(":")
        hh = int(parts[0])
        mm = int(parts[1]) if len(parts) > 1 else 0
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return time(hh, mm)
    except (ValueError, TypeError, IndexError):
        pass
    return default


def fmt_time(dt: datetime) -> str:
    """12-hour clock without the leading zero — '7:00 AM', '1:45 PM'."""
    return dt.strftime("%I:%M %p").lstrip("0")


def fmt_day(d: date) -> str:
    """'Tue, Aug 12' — with 'Today'/'Tomorrow' when that's what it is."""
    today = date.today()
    if d == today:
        return f"Today · {d.strftime('%a, %b')} {d.day}"
    if d == today + timedelta(days=1):
        return f"Tomorrow · {d.strftime('%a, %b')} {d.day}"
    return f"{d.strftime('%a, %b')} {d.day}"


def fmt_duration(minutes: int) -> str:
    """95 → '1h 35m'. Kept short: this appears inline in dense lists."""
    minutes = int(round(minutes))
    if minutes < 60:
        return f"{minutes}m"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h" if mins == 0 else f"{hours}h {mins:02d}m"
