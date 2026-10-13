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
from techdeck.core.assistant.goblin import Goblin, looks_actionable
from techdeck.core.assistant.models import (
    BLOCK_BREAK, BLOCK_BUSY, BLOCK_FIXED, BLOCK_LUNCH, BLOCK_TASK,
    ChatMessage, ChecklistItem, Note, PRIORITIES, Schedule, TaskItem,
    fmt_day, fmt_duration, fmt_time,
)
from techdeck.core.assistant import timelog
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
ACT_REMINDERS = "reminders"   # payload: {"open": bool} to open the settings
ACT_BLOCKS = "blocks"         # open the meetings/time-blocks editor
# payload: {"name": "<theme>"|""}. The brain has no settings object by design,
# so a theme change is handed to the page, which owns one.
ACT_THEME = "theme"
ACT_TIME_CSV = "time_csv"     # payload: {"range": "<timelog range key>"}


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
  /tasks [text]                     list open tasks, or just the matching ones
  /done <text>                      tick one off      /undone <text> to reopen
  /rm <text>                        delete a task
  /note [title]                     start a note      /notes  to list them
  /today  /agenda [n]               what's planned
  /find <text>                      search notes + tasks
  /export md|ics|txt                save the plan (ics imports into Outlook)
  /blocks                           meetings + standing time blocks
  /wait <text> [on <who>]           park a task on someone else
  /unwait <text>                    take it back off them
  /waiting                          everything you're waiting on
  /step <task> | <line> 20m         add a step    /steps <task>  to list them
  /clockin <text>  /clockout        the clock    /time [today|week|month]
  /log <text> 45m                   book time you forgot to clock
  /theme [name|off]                 this page's own colours
  /hours                            your working day    /set <key> <value>
  /purge                            clear out finished tasks
  /remind [on|off|<minutes>]        desktop reminders before each block
  /about                            what this page is, in short
  /help                             this list
  /clear                            wipe the terminal (this one really does delete it)

Estimates: 45m · 1h30 · 2 hours.  Priority: urgent · high · low · p1-p4.
When: today · tomorrow · friday · 8/14 · in 2 days · at 2pm · due eod.
"""

# "What is this?" is the first thing anybody types at a page they have never
# seen before, and it used to fall through to the goblin, who shrugged at it.
# Shrugging is right for a vent and wrong for a genuine question, so this is a
# real answer: what the page is, what the four parts do, and where the promise
# about not filing things comes from. Woogy's voice, because he is the one
# being asked, but every line of it is true.
ABOUT_TEXT = """\
This is the Assistant. Woogy lives in here. Hi.

It is for keeping your own day straight, and it is four things:

  Talking to Woogy   Type anything you want. Woogy answers. Nothing gets
                     saved and nothing turns into a chore, so you can yell
                     about OneDrive as much as you need to.
  Tasks              Only what you ASK for gets filed. Press “Add a task”, or
                     type  /task fix the PO sheet 45m urgent due friday
                     Or just /task, and Woogy files the last thing you said.
  Schedule           Turns those tasks into real time blocks for the day,
                     around your hours and your meetings. /schedule builds it.
                     It saves out as a calendar file that Outlook can open.
  Personal Notes     For things you want to keep. Gate codes. Numbers.

It all stays on this computer. Woogy cannot phone anybody.

/help has every command. Woogy can read. Woogy practised.
"""

# The professional theme mutes Woogy everywhere else, so it gets the same
# content with none of him in it.
ABOUT_TEXT_PLAIN = """\
The Assistant is a personal organizer built into TechDeck.

  Terminal         Free text is conversation. Nothing typed here is filed,
                   and nothing is sent anywhere.
  Tasks            Filed only on an explicit request: the “Add a task”
                   button, or  /task fix the PO sheet 45m urgent due friday
  Schedule         Builds a time-blocked plan from your open tasks, around
                   your working hours. Exports as .ics for Outlook.
  Personal Notes   Plain-text notes, searchable with /find.

Everything is stored locally on this machine.
Type /help for the full command list.
"""


class AssistantBrain:
    """Interprets terminal input against an :class:`AssistantStore`."""

    def __init__(self, store: AssistantStore, professional: bool = False,
                 themes: Optional[List[str]] = None):
        self.store = store
        self.professional = professional
        # The theme names /theme will accept. Injected by the page rather than
        # imported: core/ stays free of any ui/ import, so the whole command
        # surface still tests without a QApplication. Empty means "don't
        # validate", and the page is then the one that reports a bad name.
        self.themes = list(themes or [])
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

    def _handlers(self) -> dict:
        """Every slash command, by name. Aliases point at the same method.

        A method rather than an inline literal so a test can read it: the gate
        in tests/core/test_assistant_help_covers_commands.py checks that every
        handler here is reachable from HELP_TEXT. Four commands had shipped
        without a line in /help before that gate existed.
        """
        return {
            "help": self._cmd_help, "?": self._cmd_help,
            "about": self._cmd_about, "whatisthis": self._cmd_about,
            "explain": self._cmd_about,
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
            "blocks": self._cmd_blocks, "meetings": self._cmd_blocks,
            "wait": self._cmd_wait, "waiting": self._cmd_waiting,
            "unwait": self._cmd_unwait,
            "clockin": self._cmd_clock_in, "start": self._cmd_clock_in,
            "clockout": self._cmd_clock_out, "stop": self._cmd_clock_out,
            "time": self._cmd_time, "timelog": self._cmd_time,
            "log": self._cmd_log,
            "steps": self._cmd_steps, "step": self._cmd_step,
            "theme": self._cmd_theme,
            "clear": self._cmd_clear,
            "remind": self._cmd_remind, "reminders": self._cmd_remind,
            "notify": self._cmd_remind,
        }

    def _command(self, raw: str, now: datetime) -> Reply:
        parts = raw[1:].split(None, 1)
        name = (parts[0] if parts else "").lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        handlers = self._handlers()
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

    def _cmd_about(self, args: str, now: datetime) -> Reply:
        """What IS this. Reached by `/about` and, more importantly, by anybody
        typing "what is this" at the terminal, which used to get a shrug from
        the goblin. See `nlp._RE_ABOUT`."""
        return Reply().say(
            ABOUT_TEXT_PLAIN if self.professional else ABOUT_TEXT, ROLE_SYSTEM)

    def _cmd_remind(self, args: str, now: datetime) -> Reply:
        """`/remind` reports, `/remind on|off` toggles, `/remind 15` sets the
        warning time. Bare `/remind` also opens the settings window, since that
        is where the rest of the knobs live."""
        notify = self.store.notify
        token = args.strip().lower()

        if token in ("on", "off"):
            notify.enabled = token == "on"
            self.store.save_notify_prefs(notify)
            return Reply(dirty=True, action=ACT_REMINDERS).say(
                f"Reminders {token}.")

        digits = "".join(c for c in token if c.isdigit())
        if digits:
            notify.lead_minutes = int(digits)
            notify.enabled = True
            self.store.save_notify_prefs(
                type(notify).from_dict(notify.to_dict()))
            return Reply(dirty=True, action=ACT_REMINDERS).say(
                f"I'll warn you {self.store.notify.lead_minutes} minutes "
                f"before each block.")

        state = "on" if notify.enabled else "off"
        lines = [
            f"Reminders are {state}.",
            f"  warning        {notify.lead_minutes} min before a block",
            f"  morning plan   {'yes at ' + notify.digest_at if notify.daily_digest else 'no'}",
            f"  overdue        {'yes' if notify.overdue else 'no'}",
            f"  waiting on     {('after ' + str(notify.waiting_after_days) + ' days') if notify.waiting_followup else 'no'}",
            f"  quiet hours    {'outside your working day' if notify.quiet_outside_hours else 'never quiet'}",
            "",
            "These only arrive while TechDeck is open. For reminders that",
            "reach you with it closed, export the plan as a calendar file",
            "and open it in Outlook.",
        ]
        return Reply(action=ACT_REMINDERS, payload={"open": True}).result(
            "\n".join(lines))

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
            prefs=self.store.prefs, now=now,
            commitments=self.store.commitments))
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
        if task.waiting:
            bits.append(task.waiting_label())
        done_steps, total_steps = task.checklist_progress()
        if total_steps:
            bits.append(f"{done_steps}/{total_steps} steps")
        return " · ".join(bits)

    def _cmd_tasks(self, args: str, now: datetime) -> Reply:
        needle = args.strip()
        tasks = (self.store.find_tasks_text(needle) if needle
                 else self.store.open_tasks())
        if not tasks:
            if needle:
                return Reply().say(f"No open task mentions “{needle}”.")
            return Reply().say("Nothing open. Enjoy it while it lasts.")
        today = now.date()
        tasks.sort(key=lambda t: (-t.score(today), t.created_at))
        head = (f"{len(tasks)} open task{'s' if len(tasks) != 1 else ''}"
                + (f" mentioning “{needle}”:" if needle
                   else ", most worth doing first:"))
        lines = [head]
        for task in tasks:
            flag = ""
            due = task.deadline_date()
            if due and due <= today:
                flag = "  ⚠ due"
            elif due:
                flag = f"  · due {due.isoformat()}"
            if task.waiting:
                flag += f"  · {task.waiting_label()}"
            done_steps, total_steps = task.checklist_progress()
            if total_steps:
                flag += f"  · {done_steps}/{total_steps} steps"
            logged = task.logged_minutes(now)
            if logged:
                flag += f"  · {fmt_duration(logged)} logged"
            box = "▶" if task.is_running else "☐"
            lines.append(f"  {box} {task.label()}"
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

    # -- waiting on somebody -------------------------------------------------

    def _cmd_wait(self, args: str, now: datetime) -> Reply:
        """`/wait order the tube on Dan` parks a task on somebody else.

        The ` on <who>` tail is optional and is split off the END of the line,
        so a task whose own name contains "on" ("turn the lights on") survives.
        """
        text = args.strip()
        if not text:
            return Reply().error(
                "Which one? /wait order the 4130 tube on Dan")
        who = ""
        lowered = text.lower()
        marker = lowered.rfind(" on ")
        if marker > 0:
            candidate = text[marker + 4:].strip()
            # Only treat it as the person if what follows is short enough to be
            # a name, not the rest of a sentence.
            if candidate and len(candidate.split()) <= 4:
                who, text = candidate, text[:marker].strip()
        task = self._one_task(text)
        if isinstance(task, Reply):
            return task
        self.store.set_waiting(task.id, True, who)
        tail = f" on {who}" if who else ""
        reply = Reply(dirty=True).say(f"Parked: {task.label()}{tail}.")
        reply.system("   It won't be scheduled until you take it back off "
                     "them. /unwait when they come through.")
        return reply

    def _cmd_unwait(self, args: str, now: datetime) -> Reply:
        if not args.strip():
            return Reply().error("Which one? /unwait order the tube")
        task = self._one_task(args, include_done=False)
        if isinstance(task, Reply):
            return task
        if not task.waiting:
            return Reply().say(f"{task.label()} wasn't waiting on anybody.")
        self.store.set_waiting(task.id, False)
        return Reply(dirty=True).say(
            f"Back on you: {task.label()}. It'll be planned again.")

    def _cmd_waiting(self, args: str, now: datetime) -> Reply:
        parked = self.store.waiting_tasks()
        if not parked:
            return Reply().say("Nothing parked on anybody else.")
        today = now.date()
        parked.sort(key=lambda t: -t.waiting_days(today))
        lines = [f"{len(parked)} thing{'s' if len(parked) != 1 else ''} "
                 f"you're waiting on:"]
        for task in parked:
            days = task.waiting_days(today)
            age = ("since today" if days == 0 else
                   "1 day" if days == 1 else f"{days} days")
            who = (task.waiting_on or "").strip() or "someone"
            lines.append(f"  ⏸ {task.label()}   [{who}, {age}]")
        return Reply().result("\n".join(lines))

    # -- the clock -----------------------------------------------------------

    def _cmd_clock_in(self, args: str, now: datetime) -> Reply:
        if not args.strip():
            running = self.store.running_task()
            if running is not None:
                return Reply().say(
                    f"Already on the clock: {running.label()} "
                    f"({fmt_duration(running.logged_minutes(now))} so far).")
            return Reply().error("On what? /clockin fix the PO sheet")
        task = self._one_task(args)
        if isinstance(task, Reply):
            return task
        previous = self.store.running_task()
        self.store.clock_in(task.id, now)
        reply = Reply(dirty=True).say(
            f"Clock running on {task.label()} from {fmt_time(now)}.")
        if previous is not None and previous.id != task.id:
            reply.system(f"   Clocked out of {previous.label()} "
                         f"({fmt_duration(previous.logged_minutes(now))} "
                         f"logged).")
        return reply

    def _cmd_clock_out(self, args: str, now: datetime) -> Reply:
        running = self.store.running_task()
        if running is None:
            return Reply().say("The clock isn't running.")
        session = running.running_session()
        minutes = session.minutes(now) if session else 0
        self.store.clock_out(running.id, now)
        total = running.logged_minutes(now)
        reply = Reply(dirty=True).say(
            f"Clocked out of {running.label()}: {fmt_duration(minutes)}.")
        if total > minutes:
            reply.system(f"   {fmt_duration(total)} on it all told.")
        return reply

    def _cmd_log(self, args: str, now: datetime) -> Reply:
        """`/log fix the PO sheet 45m` books time you forgot to clock.

        The clock only catches the stretches you remembered to start, and a
        time log with holes in it is one nobody trusts enough to look at. The
        duration is read with the same grammar as everywhere else and is taken
        off the END of the line, so a task whose own name has a number in it
        ("order 4130 tube") survives.
        """
        text = args.strip()
        if not text:
            return Reply().error(
                "How long, and on what? /log fix the PO sheet 45m")
        minutes, rest = nlp.split_trailing_duration(text)
        if not minutes:
            return Reply().error(
                "I need a length on the end: /log fix the PO sheet 45m")
        task = self._one_task(rest)
        if isinstance(task, Reply):
            return task
        self.store.log_time(task.id, minutes, when=now,
                            note="added by hand")
        total = task.logged_minutes(now)
        reply = Reply(dirty=True).say(
            f"Logged {fmt_duration(minutes)} on {task.label()}.")
        reply.system(f"   {fmt_duration(total)} on it all told.")
        return reply

    def _cmd_time(self, args: str, now: datetime) -> Reply:
        """Where the time went. Defaults to this week, which is the span
        people can still remember well enough to argue with."""
        key = (args.strip().lower().replace(" ", "_") or "week")
        aliases = {"this_week": "week", "thisweek": "week",
                   "lastweek": "last_week", "this_month": "month",
                   "everything": "all", "total": "all"}
        key = aliases.get(key, key)
        if key not in {k for k, _ in timelog.RANGE_CHOICES}:
            allowed = " | ".join(k for k, _ in timelog.RANGE_CHOICES)
            return Reply().error(f"Ranges: {allowed}")
        reply = Reply(action=ACT_GOTO, payload={"tab": "time"})
        reply.result(timelog.digest(self.store.tasks, key, now))
        running = self.store.running_task()
        if running is not None:
            reply.system(f"   ▶ Still running: {running.label()}")
        return reply

    # -- steps inside a task -------------------------------------------------

    def _cmd_steps(self, args: str, now: datetime) -> Reply:
        """`/steps <task>` lists one task's checklist."""
        if not args.strip():
            return Reply().error("Which task? /steps weld shop rollout")
        task = self._one_task(args, include_done=True)
        if isinstance(task, Reply):
            return task
        if not task.checklist:
            return Reply().say(
                f"{task.label()} has no steps yet. "
                f"Add them with /step {task.label()} | <the step>")
        done, total = task.checklist_progress()
        lines = [f"{task.label()} — {done}/{total} steps:"]
        for step in task.checklist:
            box = "☑" if step.done else "☐"
            bits = []
            if step.estimate_min:
                bits.append(fmt_duration(step.estimate_min))
            if step.deadline:
                bits.append(f"due {step.deadline}")
            tail = f"   [{', '.join(bits)}]" if bits else ""
            lines.append(f"  {box} {step.label()}{tail}")
        rolled = task.checklist_minutes()
        if rolled:
            lines.append(f"  {fmt_duration(rolled)} across the steps "
                         f"(the task itself is booked for "
                         f"{fmt_duration(task.estimate_min)}).")
        return Reply().result("\n".join(lines))

    def _cmd_step(self, args: str, now: datetime) -> Reply:
        """`/step <task> | <step line>` adds one step, parsed like a task."""
        if "|" not in args:
            return Reply().error(
                "Use: /step <task> | <the step> 30m due friday")
        head, tail = args.split("|", 1)
        task = self._one_task(head, include_done=True)
        if isinstance(task, Reply):
            return task
        parsed = nlp.parse_task_line(tail.strip(), now)
        text = (parsed.get("title") or "").strip()
        if not text:
            return Reply().error("I couldn't find a step in that.")
        step = ChecklistItem(
            text=text,
            estimate_min=int(parsed.get("estimate_min") or 0),
            deadline=parsed.get("deadline"))
        self.store.add_step(task.id, step)
        done, total = task.checklist_progress()
        reply = Reply(dirty=True).say(
            f"Added step to {task.label()}: {step.label()}")
        reply.system(f"   {done}/{total} steps done.")
        return reply

    # -- this page's own colours ---------------------------------------------

    def _cmd_theme(self, args: str, now: datetime) -> Reply:
        """`/theme <name>` pins this page's colours; `/theme off` releases it.

        Handed to the page as an action rather than written here: the brain has
        no settings object, and giving it one would make the whole command
        surface need a running app to test.
        """
        word = args.strip().lower().replace(" ", "_").replace("-", "_")
        if word in ("off", "none", "app", "clear", "follow"):
            return Reply(action=ACT_THEME, payload={"name": ""}).say(
                "This page follows the app theme again.")
        names = list(self.themes)
        if not word:
            reply = Reply().say(
                "Give me a theme name and this page wears it, "
                "or /theme off to follow the app.")
            if names:
                reply.system("   " + " · ".join(names))
            return reply
        if names and word not in names:
            close = _closest(word, names)
            reply = Reply().error(f"No theme called “{word}”.")
            if close:
                reply.system(f"Did you mean {close}?")
            else:
                reply.system("   " + " · ".join(names))
            return reply
        return Reply(action=ACT_THEME, payload={"name": word}).say(
            f"This page is {word.replace('_', ' ')} now. "
            f"Everything else is untouched.")

    # -- meetings and standing blocks ----------------------------------------

    def _cmd_blocks(self, args: str, now: datetime) -> Reply:
        """List the standing claims on the day, and open the editor."""
        items = self.store.sorted_commitments()
        reply = Reply(action=ACT_BLOCKS)
        if not items:
            reply.say("No meetings or blocked-out time yet. Opening the "
                      "editor, anything you add here is time I won't plan "
                      "work into.")
            return reply
        lines = [f"{len(items)} block{'s' if len(items) != 1 else ''} "
                 f"on your day:"]
        for item in items:
            mark = "" if item.active else "   (off)"
            lines.append(f"  ■ {item.label()}   [{item.when_label()}]{mark}")
        reply.result("\n".join(lines))
        return reply

    # -- resolving a task from typed text ------------------------------------

    def _one_task(self, needle: str, include_done: bool = False):
        """One task, or a Reply explaining why not.

        Every command that takes a task by name goes through here, so "that
        matches four things" reads the same everywhere instead of each command
        inventing its own wording.
        """
        text = (needle or "").strip()
        if not text:
            return Reply().error("Which task?")
        matches = self.store.find_tasks(text, include_done=include_done)
        if not matches:
            return Reply().error(f"No task matching “{text}”.")
        if len(matches) > 1:
            reply = Reply().say(f"That matches {len(matches)} tasks, "
                                f"be a bit more specific:")
            for task in matches[:8]:
                reply.system(f"   • {task.label()}")
            return reply
        return matches[0]

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
        if intent.kind == "about":
            return self._cmd_about("", now)
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
