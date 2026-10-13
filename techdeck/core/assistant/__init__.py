"""TechDeck Assistant ("Deckhand"), the personal organizer behind the
Assistant page.

Everything in this package is pure Python with **no Qt imports**, so the
scheduling engine, the natural-language parser, and the store are all unit
testable without a QApplication. The Qt side lives in
``techdeck/ui/pages/assistant_page.py`` + ``techdeck/ui/widgets/assistant_panels.py``.

Modules:
    models, dataclasses for tasks, notes, schedules, chat messages
    store, JSON/JSONL persistence under %LOCALAPPDATA%\\TechDeck\\assistant
    nlp, rule-based parsing of dates, durations, priorities, intents
    scheduler, the time-blocking engine (deadline-bucketed WSJF packing)
    exporters, schedule → markdown / plain text / .ics
    timelog, the clocked-time report (where the week actually went)
    commands, the terminal's slash commands + free-text dispatch
"""

from techdeck.core.assistant.models import (  # noqa: F401
    ChatMessage, ChecklistItem, Commitment, Note, TaskItem, ScheduleBlock,
    DaySchedule, Schedule, SchedulePrefs, WorkSession,
    PRIORITIES, PRIORITY_LABELS,
)
from techdeck.core.assistant.store import AssistantStore  # noqa: F401
