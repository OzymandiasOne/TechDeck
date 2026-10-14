"""Assistant data model, plain dataclasses, JSON round-trippable.

Every model carries ``to_dict`` / ``from_dict`` so the store can persist them
without a serializer library, and so an older settings file that predates a
field still loads (every ``from_dict`` uses ``.get`` with the default).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, time, timedelta
from typing import Any, Dict, List, Optional, Tuple


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

# Every length and boundary in the Assistant snaps to this grid. It lives here
# rather than in the scheduler so the models can clamp against it without
# importing the engine (the engine imports the models, not the other way).
GRID_MIN = 5


def new_id(prefix: str = "") -> str:
    """Short, collision-safe id. Prefixed so a stray id in a log is readable."""
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Tolerant ISO parse. Accepts a bare date ('2026-08-12' → midnight) and
    returns None for anything unparseable rather than raising, a hand-edited
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
    for nested bullets, deliberately NOT rich text, so a note stays greppable,
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


# ── Checklist steps ──────────────────────────────────────────────────────────

@dataclass
class ChecklistItem:
    """One step inside a task.

    Steps exist so a long project can be *one* thing in the backlog with its
    own stack of work underneath, rather than eight look-alike tasks. A step
    carries its own optional estimate and its own optional date, because the
    thing people actually miss on a multi-week job is an internal milestone,
    not the final deadline.

    Steps are deliberately NOT scheduled individually: the task stays the unit
    the engine places, so a plan never fills up with fragments. The dialog can
    roll the steps' estimates up into the task's estimate on request, which is
    explicit and visible rather than silently derived.
    """
    id: str = field(default_factory=lambda: new_id("k_"))
    text: str = ""
    done: bool = False
    estimate_min: int = 0                # 0 = no estimate on this step
    deadline: Optional[str] = None       # ISO date, this step's own date
    done_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ChecklistItem":
        try:
            estimate = max(0, int(d.get("estimate_min", 0) or 0))
        except (TypeError, ValueError):
            estimate = 0
        return cls(
            id=d.get("id") or new_id("k_"),
            text=str(d.get("text", "") or ""),
            done=bool(d.get("done", False)),
            estimate_min=estimate,
            deadline=d.get("deadline"),
            done_at=d.get("done_at"),
        )

    def deadline_date(self) -> Optional[date]:
        return _parse_date(self.deadline)

    def label(self) -> str:
        return self.text.strip() or "(untitled step)"


# ── Time log ─────────────────────────────────────────────────────────────────

# A clock-out that lands inside the same minute it started is a mis-click, not
# work. Anything shorter than this is dropped rather than logged.
MIN_SESSION_MIN = 1
# A clock left running when the app closed is capped at this on the way back
# in, so a forgotten timer cannot claim a whole night.
MAX_OPEN_SESSION_MIN = 8 * 60


@dataclass
class WorkSession:
    """One stretch of time actually spent on a task.

    ``end`` is None while the clock is running, so a running timer is just an
    open session: one source of truth for "am I clocked in", and it survives a
    restart without a second flag to keep in step with it.
    """
    id: str = field(default_factory=lambda: new_id("w_"))
    start: str = field(default_factory=now_iso)
    end: Optional[str] = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WorkSession":
        return cls(
            id=d.get("id") or new_id("w_"),
            start=d.get("start") or now_iso(),
            end=d.get("end"),
            note=str(d.get("note", "") or ""),
        )

    def start_dt(self) -> Optional[datetime]:
        return _parse_dt(self.start)

    def end_dt(self) -> Optional[datetime]:
        return _parse_dt(self.end)

    @property
    def running(self) -> bool:
        return self.end is None

    def minutes(self, now: Optional[datetime] = None) -> int:
        """Length in whole minutes. A running session is measured to ``now``."""
        begin = self.start_dt()
        if begin is None:
            return 0
        finish = self.end_dt() or (now or datetime.now())
        return max(0, int((finish - begin).total_seconds() // 60))

    def day(self) -> Optional[date]:
        begin = self.start_dt()
        return begin.date() if begin else None


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
    deadline: Optional[str] = None       # ISO date or datetime, "due by"
    fixed_start: Optional[str] = None    # ISO datetime, an immovable appointment
    splittable: bool = True              # may be sliced across several blocks
    done: bool = False
    done_at: Optional[str] = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    schedule_id: Optional[str] = None    # last schedule that placed it
    # Parked on somebody else. A waiting task is NOT scheduled (planning time
    # for work you cannot start is the fastest way to stop trusting a plan),
    # but it is never silently dropped either: it is reported as waiting, and
    # it earns a follow-up nudge once it has sat too long.
    waiting: bool = False
    waiting_on: str = ""                 # who/what, free text, optional
    waiting_since: Optional[str] = None  # ISO datetime the flag went on
    # The stack of steps under one job. See ChecklistItem.
    checklist: List[ChecklistItem] = field(default_factory=list)
    # Where the time actually went. See WorkSession.
    sessions: List[WorkSession] = field(default_factory=list)

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
            waiting=bool(d.get("waiting", False)),
            waiting_on=str(d.get("waiting_on", "") or ""),
            waiting_since=d.get("waiting_since"),
            checklist=[ChecklistItem.from_dict(c)
                       for c in (d.get("checklist") or [])
                       if isinstance(c, dict)],
            sessions=[WorkSession.from_dict(w)
                      for w in (d.get("sessions") or [])
                      if isinstance(w, dict)],
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
        """WSJF, cost of delay per minute of work. Ranks a 15-minute high
        against a 3-hour critical honestly instead of always running the
        loudest task first."""
        return (self.weight * self.urgency_multiplier(today)) / max(5, self.estimate_min)

    def label(self) -> str:
        return self.title.strip() or "(untitled task)"

    # -- waiting --------------------------------------------------------------

    def waiting_label(self) -> str:
        """'waiting on Dan' / 'waiting'. Used by the chip and the nudge."""
        who = (self.waiting_on or "").strip()
        return f"waiting on {who}" if who else "waiting"

    def waiting_days(self, today: Optional[date] = None) -> int:
        """Whole days the flag has been on. 0 when it went on today or the
        stamp is missing, a nudge must never fire off an unreadable date."""
        since = _parse_date(self.waiting_since)
        if since is None:
            return 0
        return max(0, ((today or date.today()) - since).days)

    # -- checklist ------------------------------------------------------------

    def checklist_progress(self) -> Tuple[int, int]:
        """(done, total) steps."""
        total = len(self.checklist)
        return sum(1 for step in self.checklist if step.done), total

    def checklist_minutes(self) -> int:
        """Total of every step's own estimate. 0 when none of them carry one."""
        return sum(max(0, step.estimate_min) for step in self.checklist)

    def next_step(self) -> Optional[ChecklistItem]:
        """The first step still open, which is what a task row should show."""
        return next((step for step in self.checklist if not step.done), None)

    def get_step(self, step_id: str) -> Optional[ChecklistItem]:
        return next((s for s in self.checklist if s.id == step_id), None)

    # -- time log -------------------------------------------------------------

    def running_session(self) -> Optional[WorkSession]:
        return next((s for s in self.sessions if s.running), None)

    @property
    def is_running(self) -> bool:
        return self.running_session() is not None

    def logged_minutes(self, now: Optional[datetime] = None) -> int:
        """Everything clocked against this task, including a running timer."""
        return sum(session.minutes(now) for session in self.sessions)

    def logged_minutes_between(self, start: date, end: date,
                              now: Optional[datetime] = None) -> int:
        """Minutes logged on days in ``[start, end]``, inclusive.

        A session is counted on the day it STARTED. Splitting one across
        midnight would be more precise and less honest: nobody logging work
        at 11:50pm thinks of it as two days' work.
        """
        total = 0
        for session in self.sessions:
            day = session.day()
            if day is not None and start <= day <= end:
                total += session.minutes(now)
        return total


# ── Schedule ─────────────────────────────────────────────────────────────────

BLOCK_TASK = "task"
BLOCK_BREAK = "break"
BLOCK_LUNCH = "lunch"
BLOCK_FIXED = "fixed"
# Somebody else's claim on the day: a meeting, a standing huddle, a shift on
# the floor. Not a task, so it is never tickable and never counted as your
# work, it is simply time the engine is not allowed to plan into.
BLOCK_BUSY = "busy"

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass
class Commitment:
    """A standing claim on the day that is not a task.

    Before this existed the only way to tell the planner about a 9am meeting
    was to file it as a task with a locked start time, which then sat in the
    backlog asking to be ticked off. A meeting is not work you owe anybody; it
    is time you do not have. So it is its own object: no priority, no estimate,
    no done state, and it never appears in the task list.

    Two shapes, because both are real: a one-off on a given date (``day``), and
    a weekly standing commitment (``weekdays``, Monday = 0). ``weekdays`` wins
    if both are set.
    """
    id: str = field(default_factory=lambda: new_id("c_"))
    title: str = ""
    start: str = "09:00"                 # HH:MM, local
    minutes: int = 30
    day: Optional[str] = None            # ISO date for a one-off
    weekdays: List[int] = field(default_factory=list)   # 0=Mon … 6=Sun
    notes: str = ""
    active: bool = True
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Commitment":
        try:
            minutes = max(GRID_MIN, min(24 * 60, int(d.get("minutes", 30) or 30)))
        except (TypeError, ValueError):
            minutes = 30
        weekdays = []
        for value in (d.get("weekdays") or []):
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if 0 <= number <= 6 and number not in weekdays:
                weekdays.append(number)
        return cls(
            id=d.get("id") or new_id("c_"),
            title=str(d.get("title", "") or ""),
            start=str(d.get("start", "09:00") or "09:00"),
            minutes=minutes,
            day=d.get("day"),
            weekdays=sorted(weekdays),
            notes=str(d.get("notes", "") or ""),
            active=bool(d.get("active", True)),
            created_at=d.get("created_at", now_iso()),
        )

    def start_time(self) -> time:
        return parse_hhmm(self.start, time(9, 0))

    def day_date(self) -> Optional[date]:
        return _parse_date(self.day)

    @property
    def weekly(self) -> bool:
        return bool(self.weekdays)

    def occurs_on(self, when: date) -> bool:
        if not self.active:
            return False
        if self.weekly:
            return when.weekday() in self.weekdays
        own = self.day_date()
        return own is not None and own == when

    def label(self) -> str:
        return self.title.strip() or "(untitled block)"

    def when_label(self) -> str:
        """'Every Tue, Thu · 9:00 AM · 1h' / 'Fri, Oct 17 · 9:00 AM · 30m'."""
        start = datetime.combine(date.today(), self.start_time())
        tail = f"{fmt_time(start)} · {fmt_duration(self.minutes)}"
        if self.weekly:
            days = ", ".join(WEEKDAY_LABELS[n] for n in sorted(self.weekdays))
            return f"Every {days} · {tail}"
        own = self.day_date()
        if own is None:
            return f"No date yet · {tail}"
        return f"{own.strftime('%a, %b')} {own.day} · {tail}"


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

    def committed_minutes(self) -> int:
        """Time the day loses to meetings and other people's claims. Kept
        apart from work_minutes: it is not work you did, and counting it as
        such would flatter every utilisation number on the page."""
        return sum(b.minutes() for b in self.blocks if b.kind == BLOCK_BUSY)


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

    def busy_blocks(self) -> List[ScheduleBlock]:
        return [b for b in self.all_blocks() if b.kind == BLOCK_BUSY]


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
    # Smallest slice a splittable task may be cut into, below this, context
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
    """12-hour clock without the leading zero, '7:00 AM', '1:45 PM'."""
    return dt.strftime("%I:%M %p").lstrip("0")


def fmt_day(d: date) -> str:
    """'Tue, Aug 12', with 'Today'/'Tomorrow' when that's what it is."""
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
