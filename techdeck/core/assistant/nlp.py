"""Rule-based parsing for the Assistant terminal.

**There is no language model behind this**, TechDeck ships offline into a
locked-down environment, so "type what you mean" is implemented as a
deterministic grammar of durations, dates, priorities and verbs. That is a
feature, not a compromise: the same input always produces the same result, and
the terminal always echoes what it understood so a wrong guess is visible and
correctable on the spot.

Everything here is pure functions over strings, no Qt, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

# ── Durations ────────────────────────────────────────────────────────────────

_DUR_HM = re.compile(
    r"\b(\d{1,2})\s*(?:h|hr|hrs|hour|hours)\s*(\d{1,2})\s*(?:m|min|mins|minutes)?\b",
    re.I)
_DUR_H = re.compile(r"\b(\d{1,2}(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)\b", re.I)
_DUR_M = re.compile(r"\b(\d{1,3})\s*(?:m|min|mins|minute|minutes)\b", re.I)
_DUR_HALF = re.compile(r"\b(?:half\s+(?:an\s+)?hour|30\s*min)\b", re.I)
_DUR_QUARTER = re.compile(r"\b(?:quarter\s+(?:of\s+)?(?:an\s+)?hour)\b", re.I)


def parse_duration(text: str) -> Tuple[Optional[int], Optional[Tuple[int, int]]]:
    """Find a duration anywhere in ``text``.

    Returns ``(minutes, (start, end))``, the span lets the caller strip the
    duration out of a task title. Longest/most-specific pattern wins so
    "1h30" doesn't get read as "1 hour" with a stray 30.
    """
    for pattern, convert in (
        (_DUR_HM, lambda m: int(m.group(1)) * 60 + int(m.group(2))),
        (_DUR_H, lambda m: int(round(float(m.group(1)) * 60))),
        (_DUR_M, lambda m: int(m.group(1))),
        (_DUR_HALF, lambda m: 30),
        (_DUR_QUARTER, lambda m: 15),
    ):
        match = pattern.search(text)
        if match:
            minutes = convert(match)
            if 1 <= minutes <= 24 * 60:
                return minutes, match.span()
    return None, None


# ── Priority ─────────────────────────────────────────────────────────────────
# Deliberately conservative: a bare "high" only counts as a priority when it
# sits at the end of the line or right after a delimiter. Otherwise "high bay
# rack inspection" would silently lose its first word.

_PRIORITY_WORDS = {
    "critical": "critical", "urgent": "critical", "asap": "critical",
    "emergency": "critical", "p1": "critical",
    "high": "high", "important": "high", "p2": "high",
    "medium": "medium", "normal": "medium", "med": "medium", "p3": "medium",
    "low": "low", "whenever": "low", "someday": "low", "backburner": "low",
    "p4": "low",
}
_PRIORITY_ANYWHERE = {"critical", "urgent", "asap", "emergency",
                      "p1", "p2", "p3", "p4"}
_PRIORITY_RE = re.compile(
    r"(?:^|(?<=[\s;|(\[]))"
    r"(?P<word>critical|urgent|asap|emergency|important|whenever|someday|"
    r"backburner|p[1-4]|high|medium|normal|med|low)"
    r"(?:\s+(?P<qual>priority|pri))?"
    r"(?P<trail>[;|)\]]|\s|$)", re.I)


def parse_priority(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]]]:
    """Find a priority. Returns ``(priority, span)`` or ``(None, None)``.

    A word only counts when it can't be part of the task's own name:
    ``urgent``/``asap``/``p2`` are never anything else, but a bare ``high`` has
    to be qualified ("high priority"), punctuation-delimited, or sitting at the
    end of the line, otherwise "high bay rack inspection" would silently lose
    its first word.
    """
    for match in _PRIORITY_RE.finditer(text):
        word = match.group("word").lower()
        priority = _PRIORITY_WORDS.get(word)
        if priority is None:
            continue
        qualified = bool(match.group("qual"))
        hard_delim = bool(match.group("trail").strip())
        at_end = match.end("word") >= len(text.rstrip()) or \
            (qualified and match.end("qual") >= len(text.rstrip()))
        if word in _PRIORITY_ANYWHERE or qualified or hard_delim or at_end:
            # The span starts at the word, never at the leading space, so
            # cutting the priority out doesn't glue two words together.
            end = match.end("qual") if qualified else match.end("word")
            return priority, (match.start("word"), end)
    return None, None


# ── Dates and times ──────────────────────────────────────────────────────────

_WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_RE_ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_RE_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
_RE_MONTH_DAY = re.compile(
    r"\b(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|"
    r"aug|august|sep|sept|september|oct|october|nov|november|dec|december)\.?\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
_RE_DAY_MONTH = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?"
    r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|"
    r"aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b", re.I)
_RE_RELATIVE = re.compile(
    r"\bin\s+(\d{1,3})\s*(minute|minutes|min|mins|hour|hours|hr|hrs|day|days|"
    r"week|weeks|month|months)\b", re.I)
_RE_WEEKDAY = re.compile(
    r"\b(?:(next|this|coming)\s+)?"
    r"(monday|mon|tuesday|tues|tue|wednesday|wed|thursday|thurs|thur|thu|"
    r"friday|fri|saturday|sat|sunday|sun)\b", re.I)
_RE_TODAY = re.compile(r"\b(today|tonight|tonite)\b", re.I)
_RE_TOMORROW = re.compile(r"\b(tomorrow|tmrw|tmw)\b", re.I)
_RE_EOW = re.compile(r"\b(end of (?:the )?week|eow)\b", re.I)
_RE_NEXT_WEEK = re.compile(r"\bnext week\b", re.I)
_RE_EOD = re.compile(r"\b(end of (?:the )?day|eod|cob)\b", re.I)

_RE_TIME = re.compile(
    r"\b(?:at\s+|@\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)\b", re.I)
_RE_TIME_24 = re.compile(r"\b(?:at\s+|@\s*)(\d{1,2}):(\d{2})\b")
_RE_TIME_BARE = re.compile(r"\b(?:at\s+|@\s*)(\d{1,2})\b(?!\s*(?:m|min|h|hr))", re.I)
_RE_NOON = re.compile(r"\b(noon|midday)\b", re.I)
_RE_MIDNIGHT = re.compile(r"\bmidnight\b", re.I)


@dataclass
class WhenMatch:
    """What a date/time phrase resolved to."""
    day: Optional[date] = None
    at: Optional[time] = None
    spans: List[Tuple[int, int]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return self.day is None and self.at is None

    def to_datetime(self, default_time: Optional[time] = None) -> Optional[datetime]:
        if self.day is None and self.at is None:
            return None
        day = self.day or date.today()
        at = self.at or default_time
        if at is None:
            return datetime.combine(day, time(0, 0))
        return datetime.combine(day, at)


def _next_weekday(today: date, weekday: int, force_next: bool) -> date:
    """The next occurrence of ``weekday``. 'this friday' on a Friday means
    today; 'next friday' always jumps a week."""
    delta = (weekday - today.weekday()) % 7
    if force_next:
        delta = delta + 7 if delta == 0 else delta + (7 if delta < 7 else 0)
        if delta > 13:
            delta -= 7
    elif delta == 0:
        delta = 0
    return today + timedelta(days=delta)


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_when(text: str, now: Optional[datetime] = None) -> WhenMatch:
    """Pull a date and/or a time out of free text.

    The date half and the time half are matched independently and then merged,
    so "friday at 2pm", "at 2pm friday" and "2pm on 8/14" all land in the same
    place. Every matched span is recorded so the caller can strip the phrase
    from a task title.
    """
    now = now or datetime.now()
    today = now.date()
    result = WhenMatch()

    # --- date half (first match wins; most specific patterns tried first) ---
    for regex, resolve in (
        (_RE_ISO_DATE, lambda m: _safe_date(int(m.group(1)), int(m.group(2)),
                                            int(m.group(3)))),
        (_RE_MONTH_DAY, lambda m: _month_day(m.group(1), int(m.group(2)), today)),
        (_RE_DAY_MONTH, lambda m: _month_day(m.group(2), int(m.group(1)), today)),
        (_RE_SLASH_DATE, lambda m: _slash_date(m, today)),
        (_RE_RELATIVE, lambda m: _relative(m, now)),
        (_RE_TOMORROW, lambda m: today + timedelta(days=1)),
        (_RE_TODAY, lambda m: today),
        (_RE_EOW, lambda m: _next_weekday(today, 4, False)),
        (_RE_NEXT_WEEK, lambda m: today + timedelta(days=7 - today.weekday())),
        (_RE_WEEKDAY, lambda m: _next_weekday(
            today, _WEEKDAYS[m.group(2).lower()],
            (m.group(1) or "").lower() == "next")),
    ):
        match = regex.search(text)
        if match:
            resolved = resolve(match)
            if resolved is not None:
                result.day = resolved
                result.spans.append(match.span())
                break

    # "in 90 minutes" / "in 3 hours" also fixes a time of day.
    rel = _RE_RELATIVE.search(text)
    if rel and result.day is not None and rel.group(2).lower().startswith(("min", "hour", "hr")):
        target = _relative_dt(rel, now)
        if target:
            result.at = target.time().replace(second=0, microsecond=0)

    # --- time half ---
    if result.at is None:
        for regex, resolve in (
            (_RE_TIME, _time_12h),
            (_RE_TIME_24, lambda m: _safe_time(int(m.group(1)), int(m.group(2)))),
            (_RE_NOON, lambda m: time(12, 0)),
            (_RE_MIDNIGHT, lambda m: time(0, 0)),
            (_RE_TIME_BARE, _time_bare),
        ):
            match = regex.search(text)
            if match:
                resolved = resolve(match)
                if resolved is not None:
                    result.at = resolved
                    result.spans.append(match.span())
                    break

    # "eod" is a time, not a day, it means "before the day is out".
    if result.at is None:
        eod = _RE_EOD.search(text)
        if eod:
            result.at = time(16, 30)
            result.spans.append(eod.span())
            if result.day is None:
                result.day = today

    # A bare time already past today rolls to tomorrow, "at 7" typed at 3pm
    # means tomorrow morning, not eight hours ago.
    if result.day is None and result.at is not None:
        result.day = today if result.at > now.time() else today + timedelta(days=1)

    return result


def _month_day(month_word: str, day: int, today: date) -> Optional[date]:
    month = _MONTHS.get(month_word.lower().rstrip("."))
    if month is None:
        return None
    candidate = _safe_date(today.year, month, day)
    if candidate is None:
        return None
    # A month/day already ~6 months behind us almost certainly means next year.
    if (today - candidate).days > 180:
        candidate = _safe_date(today.year + 1, month, day) or candidate
    return candidate


def _slash_date(match: "re.Match[str]", today: date) -> Optional[date]:
    month, day = int(match.group(1)), int(match.group(2))
    year_part = match.group(3)
    if year_part:
        year = int(year_part)
        if year < 100:
            year += 2000
    else:
        year = today.year
    candidate = _safe_date(year, month, day)
    if candidate is None:
        return None
    if year_part is None and (today - candidate).days > 180:
        candidate = _safe_date(year + 1, month, day) or candidate
    return candidate


def _relative_dt(match: "re.Match[str]", now: datetime) -> Optional[datetime]:
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("min"):
        return now + timedelta(minutes=amount)
    if unit.startswith(("hour", "hr")):
        return now + timedelta(hours=amount)
    if unit.startswith("day"):
        return now + timedelta(days=amount)
    if unit.startswith("week"):
        return now + timedelta(weeks=amount)
    if unit.startswith("month"):
        return now + timedelta(days=30 * amount)
    return None


def _relative(match: "re.Match[str]", now: datetime) -> Optional[date]:
    dt = _relative_dt(match, now)
    return dt.date() if dt else None


def _safe_time(hour: int, minute: int) -> Optional[time]:
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return time(hour, minute)
    return None


def _time_12h(match: "re.Match[str]") -> Optional[time]:
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3).lower().replace(".", "")
    if not 1 <= hour <= 12 or not 0 <= minute <= 59:
        return None
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    return time(hour, minute)


def _time_bare(match: "re.Match[str]") -> Optional[time]:
    """'at 2', assume the working-day reading: 1–6 means the afternoon,
    7–12 the morning. Wrong occasionally, and always echoed back so it can be
    corrected in one edit."""
    hour = int(match.group(1))
    if not 0 <= hour <= 23:
        return None
    if 1 <= hour <= 6:
        hour += 12
    return time(hour, 0)


# ── Task line parsing ────────────────────────────────────────────────────────

_DUE_MARKER = re.compile(r"\b(due|by|before|deadline)\b\s*:?\s*", re.I)
_LINK_RE = re.compile(r"(https?://\S+|file:///\S+|\\\\\S+|[A-Za-z]:[\\/][^\s,;|]+)")
_LEADING_BULLET = re.compile(r"^\s*(?:[-*•+]|\d+[.)])\s+")
_NOSPLIT_RE = re.compile(r"\b(?:no ?split|one sitting|single block|uninterrupted|"
                         r"deep work|focus block)\b", re.I)


def parse_task_line(line: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Turn one typed line into task fields.

    Two accepted shapes, both optional in every part:

    * **Pipe form**, ``Fix the PO sheet | high | 45m | due friday``
      Fields after the title are sniffed, so their order doesn't matter.
    * **Inline form**, ``Fix the PO sheet 45m urgent due friday at 9am``

    Returns a dict of ``{title, priority, estimate_min, deadline, fixed_start,
    links, splittable, notes}`` with only the keys it actually found (plus a
    ``parsed`` list naming each thing it recognised, which the terminal echoes
    back so a mis-parse is obvious immediately).
    """
    now = now or datetime.now()
    raw = _LEADING_BULLET.sub("", (line or "").strip())
    out: Dict[str, Any] = {"parsed": []}
    if not raw:
        return {"title": "", "parsed": []}

    # Links come out first, a URL contains ':' and '/' that every other
    # pattern below would happily mis-read as a time or a date.
    links: List[str] = []

    def _lift_links(text: str) -> str:
        def swallow(match):
            links.append(match.group(1))
            return " "
        return _LINK_RE.sub(swallow, text)

    if "|" in raw:
        head, *fields = [part.strip() for part in raw.split("|")]
        title = _lift_links(head)
        for chunk in fields:
            if not chunk:
                continue
            chunk_clean = _lift_links(chunk)
            _absorb_field(chunk_clean, out, now)
    else:
        title = _lift_links(raw)
        title = _absorb_inline(title, out, now)

    if _NOSPLIT_RE.search(title):
        out["splittable"] = False
        out["parsed"].append("one sitting")
        title = _NOSPLIT_RE.sub(" ", title)

    if links:
        out["links"] = links
        out["parsed"].append(f"{len(links)} link{'s' if len(links) > 1 else ''}")

    out["title"] = _tidy(title)
    return out


def _absorb_field(chunk: str, out: Dict[str, Any], now: datetime) -> None:
    """Sniff one pipe-delimited field and fold it into ``out``."""
    stripped = chunk.strip()
    lowered = stripped.lower()

    if lowered in _PRIORITY_WORDS:
        out["priority"] = _PRIORITY_WORDS[lowered]
        out["parsed"].append(f"priority {out['priority']}")
        return
    if _NOSPLIT_RE.fullmatch(lowered) or lowered in ("nosplit", "no split"):
        out["splittable"] = False
        out["parsed"].append("one sitting")
        return

    minutes, _ = parse_duration(stripped)
    if minutes and not _DUE_MARKER.search(stripped):
        out["estimate_min"] = minutes
        out["parsed"].append(f"{minutes}m estimate")
        return

    _absorb_when(stripped, out, now, allow_bare_day=True)


def _absorb_inline(title: str, out: Dict[str, Any], now: datetime) -> str:
    """Strip recognised tokens out of an inline task line, back to front so the
    spans stay valid while we cut."""
    cuts: List[Tuple[int, int]] = []

    minutes, span = parse_duration(title)
    if minutes and span:
        out["estimate_min"] = minutes
        out["parsed"].append(f"{minutes}m estimate")
        cuts.append(span)

    masked = _mask(title, cuts)

    # "due <when>" / "by <when>" is a deadline; "at <time>" is an appointment.
    due_match = _DUE_MARKER.search(masked)
    if due_match:
        tail = masked[due_match.end():]
        when = parse_when(tail, now)
        due_dt = when.to_datetime()
        if due_dt is not None and when.spans:
            out["deadline"] = due_dt.date().isoformat()
            out["parsed"].append(f"due {out['deadline']}")
            offset = due_match.end()
            cuts.append((due_match.start(),
                         offset + max(e for _s, e in when.spans)))
            masked = _mask(title, cuts)

    when = parse_when(masked, now)
    start_dt = when.to_datetime()
    if start_dt is not None:
        if when.at is not None:
            out["fixed_start"] = start_dt.isoformat()
            out["parsed"].append(f"starts {out['fixed_start'].replace('T', ' ')}")
        elif "deadline" not in out and when.day is not None:
            out["deadline"] = when.day.isoformat()
            out["parsed"].append(f"due {out['deadline']}")
        cuts.extend(when.spans)

    # Priority is read LAST, against the fully-masked line. A bare "high" only
    # counts when nothing but the task name is left around it, so
    # "call Dan 1h30 high due tomorrow" has to lose its estimate and its due
    # date first, otherwise "high" sits mid-sentence, fails the delimiter
    # test, and ends up stranded in the title.
    priority, pspan = parse_priority(_mask(title, cuts))
    if priority and pspan:
        out["priority"] = priority
        out["parsed"].append(f"priority {priority}")
        cuts.append(pspan)

    return _cut(title, cuts)


def _absorb_when(chunk: str, out: Dict[str, Any], now: datetime,
                 allow_bare_day: bool) -> None:
    due = bool(_DUE_MARKER.search(chunk))
    text = _DUE_MARKER.sub(" ", chunk) if due else chunk
    when = parse_when(text, now)
    resolved = when.to_datetime()
    if resolved is None:
        return
    if when.at is not None and not due:
        out["fixed_start"] = resolved.isoformat()
        out["parsed"].append(f"starts {out['fixed_start'].replace('T', ' ')}")
    elif when.day is not None and (due or allow_bare_day):
        out["deadline"] = when.day.isoformat()
        out["parsed"].append(f"due {out['deadline']}")


def _mask(text: str, cuts: List[Tuple[int, int]]) -> str:
    """Blank out already-consumed spans (keeping offsets) so the next pattern
    can't match inside them."""
    chars = list(text)
    for start, end in cuts:
        for i in range(max(0, start), min(len(chars), end)):
            chars[i] = " "
    return "".join(chars)


def _cut(text: str, cuts: List[Tuple[int, int]]) -> str:
    return _tidy(_mask(text, cuts))


def _tidy(text: str) -> str:
    """Collapse the whitespace and dangling punctuation left behind by cutting
    tokens out of the middle of a sentence."""
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"^[\s,;:|\-–]+", "", text)
    text = re.sub(r"[\s,;:|\-–]+$", "", text)
    return text.strip()


# ── Intents ──────────────────────────────────────────────────────────────────

@dataclass
class Intent:
    """What the terminal decided a free-text line meant."""
    kind: str                                   # see INTENTS below
    text: str = ""                              # the remaining payload
    data: Dict[str, Any] = field(default_factory=dict)


INTENTS = (
    "chat",         # the default, the user is TALKING, not filing anything
    "task",         # capture a task (only ever from an explicit ask)
    "note",         # capture a note
    "schedule",     # open the schedule builder
    "agenda",       # what's on today / this week
    "list_tasks",
    "list_notes",
    "complete",
    "delete",
    "search",
    "help",
)

_RE_NOTE = re.compile(r"^\s*(?:note|jot|remember)\s*[:\-]?\s+", re.I)
# Deliberately short. Every phrase here is an unambiguous REQUEST to file
# something. "i need to…", "don't forget…" and "gotta…" used to be in this list
# and were pulled: they are things people say mid-vent ("I need to get out of
# here"), and answering a complaint with a new to-do item is exactly the
# behaviour this page was rewritten to stop doing.
_RE_TASK = re.compile(
    r"^\s*(?:add|new task|todo|task|capture|remind me to|remind me)\s*[:\-]?\s+",
    re.I)
_RE_SCHEDULE = re.compile(
    r"^\s*(?:build|make|plan|create|generate)?\s*(?:me\s+)?(?:a\s+|my\s+)?"
    r"schedule\b|^\s*plan (?:my|the) (?:day|week|morning|afternoon)\b", re.I)
_RE_AGENDA = re.compile(
    r"^\s*(?:what'?s|whats|what is|show me|show|whats on)\b.*\b"
    r"(?:today|tomorrow|this week|on|next|agenda|schedule|plan)\b", re.I)
_RE_LIST_TASKS = re.compile(
    r"^\s*(?:list|show|my)\s+(?:open\s+)?(?:tasks?|todos?|to-dos?)\b", re.I)
_RE_LIST_NOTES = re.compile(r"^\s*(?:list|show|my)\s+notes?\b", re.I)
_RE_COMPLETE = re.compile(
    r"^\s*(?:done|did|finished|complete[d]?|check off|tick off)\s*[:\-]?\s*", re.I)
_RE_DELETE = re.compile(r"^\s*(?:delete|remove|drop|forget)\s*[:\-]?\s*", re.I)
_RE_SEARCH = re.compile(r"^\s*(?:find|search|look up|where'?s)\s*[:\-]?\s*", re.I)
_RE_HELP = re.compile(r"^\s*(?:help|what can you do|commands?)\s*\??\s*$", re.I)


def parse_intent(text: str) -> Intent:
    """Classify one free-text terminal line.

    Order matters: the more specific a phrase is, the earlier it is tested.

    **A line that matches nothing is `chat`, the user is talking.** Nothing is
    filed on a guess. Capture requires an explicit ask (`/task`, "add …",
    "remind me to …"), the Add a task button, or the Tasks tab. The first
    build defaulted to capturing everything, which turned "this PO sheet is a
    nightmare" into a chore of that name; a tool that answers a complaint with
    a to-do item is a tool people stop talking to.
    """
    raw = (text or "").strip()
    if not raw:
        return Intent("help")

    if _RE_HELP.match(raw):
        return Intent("help")
    if raw.lstrip().startswith(("- ", "* ", "• ")) or "\n" in raw:
        return Intent("note", raw)
    match = _RE_NOTE.match(raw)
    if match:
        return Intent("note", raw[match.end():])
    if _RE_SCHEDULE.search(raw):
        return Intent("schedule", raw)
    if _RE_LIST_TASKS.match(raw):
        return Intent("list_tasks", raw)
    if _RE_LIST_NOTES.match(raw):
        return Intent("list_notes", raw)
    if _RE_AGENDA.match(raw):
        return Intent("agenda", raw)
    match = _RE_COMPLETE.match(raw)
    if match:
        return Intent("complete", raw[match.end():])
    match = _RE_DELETE.match(raw)
    if match:
        return Intent("delete", raw[match.end():])
    match = _RE_SEARCH.match(raw)
    if match:
        return Intent("search", raw[match.end():])
    match = _RE_TASK.match(raw)
    if match:
        return Intent("task", raw[match.end():], {"explicit": True})

    return Intent("chat", raw)


def parse_bullet_block(text: str, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Parse a pasted block of bullets into task field-dicts, one per non-empty
    line. Backs the wizard's 'paste your list' box: someone with a list already
    written in Teams or Notepad shouldn't have to retype it into a grid."""
    now = now or datetime.now()
    out: List[Dict[str, Any]] = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        parsed = parse_task_line(line, now)
        if parsed.get("title"):
            out.append(parsed)
    return out
