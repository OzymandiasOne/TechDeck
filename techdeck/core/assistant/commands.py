"""The terminal's brain: one typed line in, a reply plus an optional UI action out.

Deliberately Qt-free. ``AssistantBrain.handle`` returns a :class:`Reply`, the
lines to print and, when the request needs the interface to do something
(open the schedule builder, jump to a tab, put up a save dialog), a named
``action`` for the page to carry out. That split is what makes the whole
command surface testable without a window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from techdeck.core.assistant import nlp
from techdeck.core.assistant.goblin import NUDGE as GOBLIN_NUDGE
from techdeck.core.assistant.goblin import Goblin, looks_actionable
from techdeck.core.assistant.models import (
    BLOCK_BREAK, BLOCK_FIXED, BLOCK_LUNCH, BLOCK_TASK,
    ChatMessage, Note, PRIORITIES, Schedule, TaskItem,
    fmt_day, fmt_duration, fmt_time,
)
from techdeck.core.assistant.scheduler import (
    ScheduleRequest, build_schedule, resolve_range, summarize,
)
from techdeck.core.assistant.store import AssistantStore

# Roles map to colours in the terminal view.
ROLE_DECK = "deck"
ROLE_SYSTEM = "system"
ROLE_ERROR = "error"
ROLE_RESULT = "result"

# Actions the page performs on the brain's behalf.
ACT_OPEN_WIZARD = "open_wizard"
ACT_GOTO = "goto"            # payload: {"tab": "notes"|"schedule"|"tasks"|"terminal"}
ACT_EXPORT = "export"        # payload: {"format": "md"|"ics"|"txt"}
ACT_CLEAR = "clear"
ACT_REFRESH = "refresh"
ACT_EDIT_NOTE = "edit_note"  # payload: {"note_id": ...}
ACT_PREFS = "prefs"


@dataclass
class Reply:
    lines: List[Tuple[str, str]] = field(default_factory=list)
    action: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    # Set when the reply changed stored data, so the page knows to re-render
    # its panels without every handler having to say so.
    dirty: bool = False
    # The user said something that COULD be a task. The page offers a one-click
    # "make that a task" chip, it never files anything on this alone.
    offer_task: bool = False

    def say(self, text: str, role: str = ROLE_DECK) -> "Reply":
        self.lines.append((role, text))
        return self

    def error(self, text: str) -> "Reply":
        return self.say(text, ROLE_ERROR)

    def result(self, text: str) -> "Reply":
        return self.say(text, ROLE_RESULT)

    def system(self, text: str) -> "Reply":
        return self.say(text, ROLE_SYSTEM)


HELP_TEXT = """\
Talk to me. Nothing you say gets filed unless you ask for it.

  Just type                 →  we're just talking. Vent away.
    this PO sheet is a nightmare
    onedrive ate the file AGAIN

  To actually file something:
    press “Add a task”, or
    /task fix the PO sheet 45m urgent due friday
    /task                             ← files the last thing you said
    remind me to call Dan at 9am
    note: gate code is 4417
    - a line starting with a dash becomes a note

  /schedule [today|tomorrow|week]   build a plan (opens the builder)
  /replan                           rebuild the last plan from today's tasks
  /task <line>                      add a task explicitly
  /tasks                            list open tasks
  /done <text>                      tick one off      /undone <text> to reopen
  /rm <text>                        delete a task
  /note [title]                     start a note      /notes  to list them
  /today  /agenda [n]               what's planned
  /find <text>                      search notes + tasks
  /export md|ics|txt                save the plan (ics imports into Outlook)
  /hours                            your working day    /set <key> <value>
  /purge                            clear out finished tasks
  /clear                            wipe the terminal (this one really does delete it)

Estimates: 45m · 1h30 · 2 hours.  Priority: urgent · high · low · p1-p4.
When: today · tomorrow · friday · 8/14 · in 2 days · at 2pm · due eod.
"""


class AssistantBrain:
    """Interprets terminal input against an :class:`AssistantStore`."""

    def __init__(self, store: AssistantStore, professional: bool = False):
        self.store = store
        # The thing that answers when the user just wants to talk.
        self.goblin = Goblin(professional=professional)
        # The last free-text line, so a bare `/task` (or the page's "make that
        # a task" chip) can promote something already said without retyping it.
        self._last_said = ""

    # ── entry point ──────────────────────────────────────────────────────────

    def handle(self, text: str, now: Optional[datetime] = None) -> Reply:
        now = now or datetime.now()
        raw = (text or "").strip()
        if not raw:
            return Reply()
        if raw.startswith("/"):
            return self._command(raw, now)
        return self._freeform(raw, now)

    # ── slash commands ───────────────────────────────────────────────────────

    def _command(self, raw: str, now: datetime) -> Reply:
        parts = raw[1:].split(None, 1)
        name = (parts[0] if parts else "").lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        handlers = {
            "help": self._cmd_help, "?": self._cmd_help,
            "schedule": self._cmd_schedule, "plan": self._cmd_schedule,
            "replan": self._cmd_replan,
            "task": self._cmd_task, "todo": self._cmd_task, "add": self._cmd_task,
            "tasks": self._cmd_tasks, "todos": self._cmd_tasks,
            "done": self._cmd_done, "undone": self._cmd_undone,
            "rm": self._cmd_remove, "delete": self._cmd_remove,
            "note": self._cmd_note, "notes": self._cmd_notes,
            "today": self._cmd_today, "agenda": self._cmd_agenda,
            "find": self._cmd_find, "search": self._cmd_find,
            "export": self._cmd_export,
            "hours": self._cmd_hours, "prefs": self._cmd_hours,
            "set": self._cmd_set,
            "purge": self._cmd_purge,
            "clear": self._cmd_clear,
        }
        handler = handlers.get(name)
        if handler is None:
            reply = Reply().error(f"No command called /{name}.")
            close = _closest(name, handlers.keys())
            if close:
                reply.system(f"Did you mean /{close}?")
            else:
                reply.system("Type /help to see what's available.")
            return reply
        return handler(args, now)

    def _cmd_help(self, args: str, now: datetime) -> Reply:
        return Reply().say(HELP_TEXT, ROLE_SYSTEM)

    def _cmd_clear(self, args: str, now: datetime) -> Reply:
        return Reply(action=ACT_CLEAR).system(
            "Terminal cleared. That wipes the saved history too.")

    # -- scheduling ----------------------------------------------------------

    _RANGE_WORDS = {
        "today": "today", "now": "rest_of_today", "rest": "rest_of_today",
        "tomorrow": "tomorrow", "week": "this_week",
        "thisweek": "this_week", "this": "this_week",
        "next": "next_week", "nextweek": "next_week",
    }

    def _cmd_schedule(self, args: str, now: datetime) -> Reply:
        """Open the builder. A range word pre-selects the coverage step so
        `/schedule tomorrow` lands on the task list with one keystroke."""
        key = self._RANGE_WORDS.get(args.strip().lower().replace(" ", ""), "")
        payload = {"range": key} if key else {}
        reply = Reply(action=ACT_OPEN_WIZARD, payload=payload)
        open_count = len(self.store.open_tasks())
        if open_count:
            reply.say(f"Opening the schedule builder with your "
                      f"{open_count} open task{'s' if open_count != 1 else ''} "
                      f"loaded in.")
        else:
            reply.say("Opening the schedule builder. Add your tasks in step 2.")
        return reply

    def _cmd_replan(self, args: str, now: datetime) -> Reply:
        """Rebuild the most recent plan's range against the CURRENT task list.
        This is the one you want at 10am when the morning went sideways."""
        previous = self.store.latest_schedule()
        tasks = self.store.open_tasks()
        if not tasks:
            return Reply().say("Nothing open to plan. Add a task first.")

        if previous and previous.days:
            first = previous.days[0].date_obj() or now.date()
            last = previous.days[-1].date_obj() or first
            span = max(0, (last - first).days)
            start = now.date()
            end = start + timedelta(days=span)
        else:
            start = end = now.date()

        schedule = build_schedule(ScheduleRequest(
            tasks=tasks, start_day=start, end_day=end,
            prefs=self.store.prefs, now=now))
        self.store.add_schedule(schedule)
        reply = Reply(action=ACT_GOTO, payload={"tab": "schedule"}, dirty=True)
        reply.say(f"Replanned from right now ({fmt_time(now)}).")
        reply.result(summarize(schedule))
        return reply

    def _cmd_today(self, args: str, now: datetime) -> Reply:
        return self._agenda_for(now.date(), now.date(), now, "Today")

    def _cmd_agenda(self, args: str, now: datetime) -> Reply:
        days = 1
        token = args.strip().lower()
        if token.isdigit():
            days = max(1, min(14, int(token)))
        elif token in ("week", "this week"):
            days = 7
        elif token == "tomorrow":
            day = now.date() + timedelta(days=1)
            return self._agenda_for(day, day, now, "Tomorrow")
        start = now.date()
        return self._agenda_for(start, start + timedelta(days=days - 1), now,
                                "The next few days" if days > 1 else "Today")

    def _agenda_for(self, start: date, end: date, now: datetime,
                    label: str) -> Reply:
        """Read the saved plan for a date range, this reports what was PLANNED,
        it doesn't invent a new plan. /replan is the one that re-solves."""
        schedule = self.store.latest_schedule()
        reply = Reply()
        if schedule is None:
            reply.say("No plan saved yet. Type /schedule to build one.")
            return reply

        printed = 0
        for day_plan in schedule.days:
            day_date = day_plan.date_obj()
            if day_date is None or not (start <= day_date <= end):
                continue
            planned = [b for b in day_plan.blocks
                       if b.kind in (BLOCK_TASK, BLOCK_FIXED)]
            if not planned:
                continue
            printed += 1
            lines = [fmt_day(day_date)]
            for block in day_plan.blocks:
                marker = {BLOCK_TASK: "•", BLOCK_FIXED: "◆",
                          BLOCK_LUNCH: "·", BLOCK_BREAK: "·"}.get(block.kind, "•")
                now_marker = ""
                s, e = block.start_dt(), block.end_dt()
                if s and e and s <= now < e:
                    now_marker = "   ← you are here"
                suffix = (f"  (part {block.part} of {block.part_count})"
                          if block.part and block.part_count > 1 else "")
                lines.append(f"  {block.time_range():<20} {marker} "
                             f"{block.title}{suffix}{now_marker}")
            reply.result("\n".join(lines))

        if not printed:
            reply.say(f"{label}: nothing planned in the saved schedule "
                      f"({schedule.range_label}). /replan rebuilds it from now.")
        return reply

    # -- tasks ---------------------------------------------------------------

    def _cmd_task(self, args: str, now: datetime) -> Reply:
        """`/task <line>` files it. A bare `/task` promotes the last thing you
        said, which is the point of not auto-filing: you can talk freely, and
        if it turns out one of those lines was actually a job, it's one word
        away instead of a retype."""
        if not args:
            if not self._last_said:
                return Reply().error(
                    "Give me something to do: /task fix the PO sheet 45m")
            said, self._last_said = self._last_said, ""
            # Cleared so a second press can't file the same line twice.
            return self._capture_task(said, now, promoted=True)
        return self._capture_task(args, now)

    def _capture_task(self, text: str, now: datetime,
                      promoted: bool = False) -> Reply:
        parsed = nlp.parse_task_line(text, now)
        title = parsed.get("title", "").strip()
        if not title:
            return Reply().error("I couldn't find a task in that.")

        task = TaskItem(
            title=title,
            priority=parsed.get("priority", "medium"),
            estimate_min=int(parsed.get("estimate_min", 30)),
            deadline=parsed.get("deadline"),
            fixed_start=parsed.get("fixed_start"),
            splittable=bool(parsed.get("splittable", True)),
            links=list(parsed.get("links", [])),
        )
        self.store.add_task(task)

        reply = Reply(dirty=True)
        reply.say(("Fine. Filed: " if promoted else "Added: ") + task.label())
        reply.system("   " + self._describe(task))
        return reply

    @staticmethod
    def _describe(task: TaskItem) -> str:
        bits = [f"{fmt_duration(task.estimate_min)}", task.priority]
        if task.deadline:
            bits.append(f"due {task.deadline}")
        if task.fixed_start:
            start = task.fixed_datetime()
            if start:
                bits.append(f"at {fmt_time(start)} on {start.date().isoformat()}")
        if not task.splittable:
            bits.append("one sitting")
        if task.links:
            bits.append(f"{len(task.links)} link(s)")
        return " · ".join(bits)

    def _cmd_tasks(self, args: str, now: datetime) -> Reply:
        tasks = self.store.open_tasks()
        if not tasks:
            return Reply().say("Nothing open. Enjoy it while it lasts.")
        today = now.date()
        tasks.sort(key=lambda t: (-t.score(today), t.created_at))
        lines = [f"{len(tasks)} open task{'s' if len(tasks) != 1 else ''}, "
                 f"most worth doing first:"]
        for task in tasks:
            flag = ""
            due = task.deadline_date()
            if due and due <= today:
                flag = "  ⚠ due"
            elif due:
                flag = f"  · due {due.isoformat()}"
            lines.append(f"  ☐ {task.label()}"
                         f"   [{task.priority}, {fmt_duration(task.estimate_min)}]{flag}")
        total = sum(t.estimate_min for t in tasks)
        lines.append(f"  {fmt_duration(total)} of work on the books.")
        return Reply().result("\n".join(lines))

    def _cmd_done(self, args: str, now: datetime) -> Reply:
        return self._toggle_done(args, True)

    def _cmd_undone(self, args: str, now: datetime) -> Reply:
        return self._toggle_done(args, False)

    def _toggle_done(self, needle: str, done: bool) -> Reply:
        if not needle.strip():
            return Reply().error("Which one? /done fix the po sheet")
        matches = self.store.find_tasks(needle, include_done=not done)
        if not matches:
            return Reply().error(f"No open task matching “{needle.strip()}”.")
        if len(matches) > 1:
            reply = Reply().say(f"That matches {len(matches)} tasks, "
                                f"be a bit more specific:")
            for task in matches[:8]:
                reply.system(f"   • {task.label()}")
            return reply
        task = matches[0]
        self.store.set_done(task.id, done)
        verb = "Done" if done else "Reopened"
        return Reply(dirty=True).say(f"{verb}: {task.label()}")

    def _cmd_remove(self, args: str, now: datetime) -> Reply:
        if not args.strip():
            return Reply().error("Which one? /rm fix the po sheet")
        matches = self.store.find_tasks(args, include_done=True)
        if not matches:
            return Reply().error(f"No task matching “{args.strip()}”.")
        if len(matches) > 1:
            reply = Reply().say(f"That matches {len(matches)} tasks, "
                                f"be a bit more specific:")
            for task in matches[:8]:
                reply.system(f"   • {task.label()}")
            return reply
        task = matches[0]
        self.store.delete_task(task.id)
        return Reply(dirty=True).say(f"Deleted: {task.label()}")

    def _cmd_purge(self, args: str, now: datetime) -> Reply:
        removed = self.store.purge_done(keep_days=0)
        if not removed:
            return Reply().say("Nothing finished to clear out.")
        return Reply(dirty=True).say(
            f"Cleared {removed} finished task{'s' if removed != 1 else ''}.")

    # -- notes ---------------------------------------------------------------

    def _cmd_note(self, args: str, now: datetime) -> Reply:
        title = args.strip() or f"Note {now.strftime('%b %d, %I:%M %p').replace(' 0', ' ')}"
        note = Note(title=title[:80], body="")
        self.store.add_note(note)
        return Reply(action=ACT_EDIT_NOTE, payload={"note_id": note.id},
                     dirty=True).say(f"Started “{note.title}” in Personal Notes.")

    def _capture_note(self, text: str, now: datetime) -> Reply:
        """Free-text note capture. The first line becomes the title when it
        reads like one; otherwise the note is stamped with the time and the
        whole thing is the body, nothing typed is ever thrown away."""
        body = text.rstrip()
        lines = body.splitlines()
        first = lines[0].strip() if lines else ""
        looks_like_title = (first and not first.startswith(("-", "*", "•"))
                            and len(first) <= 70 and len(lines) > 1)
        if looks_like_title:
            title = first
            body = "\n".join(lines[1:]).strip("\n")
        else:
            title = (first[:60] if first else
                     f"Note {now.strftime('%b %d')}")
            title = title.lstrip("-*• ").strip() or f"Note {now.strftime('%b %d')}"

        note = Note(title=title, body=body)
        self.store.add_note(note)
        reply = Reply(dirty=True).say(f"Saved to Personal Notes: “{note.title}”")
        reply.system("   Open the Personal Notes tab to keep writing.")
        return reply

    def _cmd_notes(self, args: str, now: datetime) -> Reply:
        notes = self.store.sorted_notes()
        if not notes:
            return Reply(action=ACT_GOTO, payload={"tab": "notes"}).say(
                "No notes yet. /note starts one.")
        lines = [f"{len(notes)} note{'s' if len(notes) != 1 else ''}:"]
        for note in notes[:20]:
            pin = "📌 " if note.pinned else "   "
            preview = note.preview(60)
            lines.append(f" {pin}{note.title}"
                         + (f"\n        {preview}" if preview else ""))
        if len(notes) > 20:
            lines.append(f"   …and {len(notes) - 20} more on the Personal Notes tab.")
        return Reply(action=ACT_GOTO, payload={"tab": "notes"}).result("\n".join(lines))

    # -- search --------------------------------------------------------------

    def _cmd_find(self, args: str, now: datetime) -> Reply:
        needle = args.strip().lower()
        if not needle:
            return Reply().error("Find what? /find rev c")
        reply = Reply()
        hits = 0

        tasks = [t for t in self.store.tasks
                 if needle in t.title.lower() or needle in (t.notes or "").lower()]
        if tasks:
            hits += len(tasks)
            lines = ["Tasks:"]
            for task in tasks[:10]:
                box = "☑" if task.done else "☐"
                lines.append(f"  {box} {task.label()}   [{self._describe(task)}]")
            reply.result("\n".join(lines))

        notes = [n for n in self.store.notes
                 if needle in n.title.lower() or needle in n.body.lower()]
        if notes:
            hits += len(notes)
            lines = ["Notes:"]
            for note in notes[:10]:
                lines.append(f"  • {note.title}")
                for body_line in note.body.splitlines():
                    if needle in body_line.lower():
                        lines.append(f"        {body_line.strip()[:90]}")
                        break
            reply.result("\n".join(lines))

        if not hits:
            reply.say(f"Nothing matching “{args.strip()}”.")
        return reply

    # -- preferences ---------------------------------------------------------

    def _cmd_hours(self, args: str, now: datetime) -> Reply:
        prefs = self.store.prefs
        lines = [
            "Your working day:",
            f"  start           {prefs.day_start}",
            f"  end             {prefs.day_end}",
            f"  lunch           {prefs.lunch_start} for {prefs.lunch_minutes}m",
            f"  weekends        {'yes' if prefs.include_weekends else 'no'}",
            f"  focus block     {prefs.focus_block_min}m, then a "
            f"{prefs.breather_min}m breather",
            f"  smallest slice  {prefs.min_chunk_min}m",
            f"  estimate buffer +{prefs.buffer_pct}%",
            "",
            "Change one with:  /set start 06:30   ·   /set buffer 20",
        ]
        return Reply(action=ACT_PREFS).result("\n".join(lines))

    _PREF_KEYS = {
        "start": "day_start", "day_start": "day_start",
        "end": "day_end", "day_end": "day_end",
        "lunch": "lunch_start", "lunch_start": "lunch_start",
        "lunchlen": "lunch_minutes", "lunch_minutes": "lunch_minutes",
        "weekends": "include_weekends",
        "focus": "focus_block_min", "focus_block": "focus_block_min",
        "breather": "breather_min", "break": "breather_min",
        "slice": "min_chunk_min", "min_chunk": "min_chunk_min",
        "buffer": "buffer_pct",
    }

    def _cmd_set(self, args: str, now: datetime) -> Reply:
        parts = args.split(None, 1)
        if len(parts) < 2:
            return Reply().error("Usage: /set start 06:30")
        key = self._PREF_KEYS.get(parts[0].strip().lower())
        if key is None:
            return Reply().error(
                f"Don't know the setting “{parts[0]}”. /hours lists them.")
        value_text = parts[1].strip()
        prefs = self.store.prefs

        if key == "include_weekends":
            value: Any = value_text.lower() in ("1", "yes", "y", "true", "on")
        elif key in ("day_start", "day_end", "lunch_start"):
            value = value_text
        else:
            digits = "".join(c for c in value_text if c.isdigit())
            if not digits:
                return Reply().error(f"“{value_text}” isn't a number.")
            value = int(digits)

        setattr(prefs, key, value)
        # Round-trip through from_dict so the clamps in SchedulePrefs apply and
        # a typo like "/set buffer 900" can't poison every future plan.
        cleaned = type(prefs).from_dict(prefs.to_dict())
        self.store.save_prefs(cleaned)
        return Reply(dirty=True, action=ACT_PREFS).say(
            f"{key.replace('_', ' ')} → {getattr(cleaned, key)}")

    # -- export --------------------------------------------------------------

    def _cmd_export(self, args: str, now: datetime) -> Reply:
        fmt = (args.strip().lower() or "md").lstrip(".")
        if fmt in ("markdown", "md"):
            fmt = "md"
        elif fmt in ("ics", "cal", "calendar", "outlook"):
            fmt = "ics"
        elif fmt in ("txt", "text"):
            fmt = "txt"
        else:
            return Reply().error("Export as what? md, ics, or txt.")
        if self.store.latest_schedule() is None:
            return Reply().error("No plan to export yet. /schedule builds one.")
        note = ("  (an .ics opens straight into Outlook)" if fmt == "ics" else "")
        return Reply(action=ACT_EXPORT, payload={"format": fmt}).say(
            f"Exporting the latest plan as .{fmt}.{note}")

    # ── free text ────────────────────────────────────────────────────────────

    def _freeform(self, raw: str, now: datetime) -> Reply:
        intent = nlp.parse_intent(raw)

        if intent.kind == "help":
            return self._cmd_help("", now)
        if intent.kind == "note":
            return self._capture_note(intent.text or raw, now)
        if intent.kind == "schedule":
            return self._cmd_schedule("", now)
        if intent.kind == "agenda":
            return self._agenda_intent(raw, now)
        if intent.kind == "list_tasks":
            return self._cmd_tasks("", now)
        if intent.kind == "list_notes":
            return self._cmd_notes("", now)
        if intent.kind == "complete":
            return self._toggle_done(intent.text, True)
        if intent.kind == "delete":
            return self._cmd_remove(intent.text, now)
        if intent.kind == "search":
            return self._cmd_find(intent.text, now)
        if intent.kind == "task":
            return self._capture_task(intent.text or raw, now)
        return self._chat(raw)

    def _chat(self, raw: str) -> Reply:
        """The default. The user is talking, so listen, answer, and file
        NOTHING. This is the whole contract of the page: the terminal is a
        place you can complain at 6:40am without it turning your complaint
        into a chore."""
        self._last_said = raw
        reply = Reply()
        reply.say(self.goblin.respond(raw))
        if self.goblin.wants_nudge():
            reply.system(f"   {GOBLIN_NUDGE}")
        # Offer, never act: the page shows a one-click chip and the user
        # decides. Venting is explicitly excluded from "looks actionable".
        reply.offer_task = looks_actionable(raw)
        return reply

    def _agenda_intent(self, raw: str, now: datetime) -> Reply:
        when = nlp.parse_when(raw, now)
        if when.day:
            return self._agenda_for(when.day, when.day, now, fmt_day(when.day))
        if "week" in raw.lower():
            start = now.date()
            return self._agenda_for(start, start + timedelta(days=6), now,
                                    "This week")
        return self._cmd_today("", now)


def _closest(name: str, options) -> Optional[str]:
    """Cheap did-you-mean: shared-prefix length, no edit-distance library."""
    best, best_score = None, 0
    for option in options:
        score = len(_common_prefix(name, option))
        if score > best_score:
            best, best_score = option, score
    return best if best_score >= 2 else None


def _common_prefix(a: str, b: str) -> str:
    out = []
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        out.append(ca)
    return "".join(out)
