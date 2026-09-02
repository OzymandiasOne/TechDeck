"""Java Tutor - lesson names.

`history.py` deliberately stores nothing: it reads Claude Code's own transcripts
and takes the title from the `ai-title` entry Claude writes, falling back to a
slice of the first message. Those files belong to Claude Code, so a rename must
NOT be written into them - a transcript rewritten underneath a running session
is a good way to lose a lesson.

So names live here instead, in a sidecar beside the Dev Board's state:

    %LOCALAPPDATA%\\TechDeck\\devkit\\java_tutor_titles.json

Two things are stored:

`titles`   session id -> the name to show. Set by a rename, or claimed from
           `pending` when a new lesson starts.
`pending`  a name with no session yet. Claude Code writes this when a lesson is
           PLANNED, before the tutor is even open; the next new lesson claims it
           and clears it. That is what "name the chats after our lesson plans"
           means in practice - the plan exists before the session id does.

Precedence when the sidebar draws a lesson:

    stored title  >  Claude's ai-title  >  first-message preview

A stored title always wins, which is what makes a rename stick: nothing ever
re-applies a plan name over one the user typed.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_VERSION = 1


def _state_path() -> Path:
    from techdeck.core.settings import SettingsManager
    base = SettingsManager().settings_dir / "devkit"
    base.mkdir(parents=True, exist_ok=True)
    return base / "java_tutor_titles.json"


class TitleStore:
    """Custom lesson names. Every mutation saves atomically."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else _state_path()
        self.titles: dict[str, str] = {}
        self.pending: str = ""
        self._load()

    # ---- persistence -----------------------------------------------------

    def _load(self):
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            # A corrupt sidecar must never take the tutor down with it - the
            # lessons themselves are fine, they just fall back to auto names.
            logger.warning("java_tutor: titles unreadable (%s); ignoring", exc)
            return
        raw = data.get("titles")
        if isinstance(raw, dict):
            self.titles = {str(k): str(v) for k, v in raw.items() if str(v).strip()}
        self.pending = str(data.get("pending") or "").strip()

    def save(self):
        payload = {"version": STATE_VERSION, "titles": self.titles,
                   "pending": self.pending}
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, self.path)

    # ---- names -----------------------------------------------------------

    def get(self, session_id: str) -> str:
        return self.titles.get(session_id, "")

    def rename(self, session_id: str, title: str):
        """Name one lesson. An empty title clears it back to the auto name."""
        title = " ".join(str(title).split())
        if title:
            self.titles[session_id] = title
        else:
            self.titles.pop(session_id, None)
        self.save()

    # ---- the planned-lesson handoff --------------------------------------

    def set_pending(self, title: str):
        """Name the NEXT lesson, before it exists. Claude Code calls this when
        a lesson is planned; the tutor claims it on the next new session."""
        self.pending = " ".join(str(title).split())
        self.save()

    def claim_pending(self, session_id: str) -> str:
        """Bind any pending name to this session and clear it. Returns the name
        claimed, or "" if there was none.

        A session that ALREADY has a name does not claim - that covers resuming
        an old lesson, where `session_ready` fires with a known id and the
        pending plan is still waiting for a genuinely new one.
        """
        if not self.pending or self.get(session_id):
            return ""
        title = self.pending
        self.titles[session_id] = title
        self.pending = ""
        self.save()
        return title
