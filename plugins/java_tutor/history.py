"""
Java Tutor - past lessons.

Claude Code already writes every conversation to disk as newline-delimited
JSON, one file per session, under:

    %USERPROFILE%\\.claude\\projects\\<slugged-cwd>\\<session-id>.jsonl

So this module stores nothing. It reads what is already there: lists the
lessons, searches them, and loads one back for re-reading. The filename is the
session id, which is also what `claude --resume` takes - so "open an old lesson
and keep going" costs nothing extra.

Only sessions whose working directory was the tutor folder appear here. That is
deliberate: TechDeck sessions and other project work are not lessons.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Long-path-safe filesystem checks (Hard Rule 14). A raw .is_dir() answers
# False for a folder that exists once the path passes 260 characters.
try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:  # standalone / headless testing
    import sys as _sys
    import pathlib as _pl
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

def transcript_dir(cwd: Path) -> Path:
    """Folder holding the transcripts for sessions run in `cwd`.

    Claude Code slugs the working directory by replacing every character that
    is not a letter or digit with a dash: C:\\Dev\\Code Tutor -> C--Dev-Code-Tutor.
    """
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
    return Path.home() / ".claude" / "projects" / slug


@dataclass
class Message:
    role: str          # "user" or "assistant"
    text: str
    timestamp: str = ""


@dataclass
class Conversation:
    session_id: str
    path: Path
    title: str = ""
    preview: str = ""
    started: str = ""
    last_active: float = 0.0
    turns: int = 0

    @property
    def when(self) -> str:
        """Short human date for the sidebar, e.g. 'Sep 1, 2:37 PM'."""
        if not self.last_active:
            return ""
        try:
            return datetime.fromtimestamp(self.last_active).strftime("%b %-d, %-I:%M %p")
        except ValueError:
            # Windows strftime has no %-d / %-I
            return datetime.fromtimestamp(self.last_active).strftime("%b %d, %I:%M %p").replace(" 0", " ")


def _block_text(content) -> str:
    """Flatten a message's content down to the plain text a human typed or read.

    Tool calls and tool results are skipped: they are the tutor's plumbing, not
    part of the lesson.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    out = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            out.append(block.get("text") or "")
    return "".join(out)


def _iter_entries(path: Path):
    """Yield parsed JSON objects from a transcript, skipping unreadable lines."""
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        logger.warning("java_tutor: cannot read %s (%s)", path.name, exc)


def read_messages(path: Path) -> list[Message]:
    """Every human-visible message in a transcript, in order."""
    messages: list[Message] = []
    for entry in _iter_entries(path):
        if entry.get("type") not in ("user", "assistant"):
            continue
        # Subagent chatter is not part of the lesson.
        if entry.get("isSidechain"):
            continue
        msg = entry.get("message")
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _block_text(msg.get("content")).strip()
        if not text:
            continue
        messages.append(Message(role=role, text=text, timestamp=entry.get("timestamp") or ""))
    return messages


def _summarise(path: Path) -> Conversation | None:
    """Build the sidebar entry for one transcript."""
    session_id = path.stem
    title = ""
    first_user = ""
    started = ""
    turns = 0

    for entry in _iter_entries(path):
        etype = entry.get("type")
        if etype == "ai-title":
            title = (entry.get("aiTitle") or "").strip()
            continue
        if etype not in ("user", "assistant") or entry.get("isSidechain"):
            continue
        msg = entry.get("message")
        if not isinstance(msg, dict):
            continue
        text = _block_text(msg.get("content")).strip()
        if not text:
            continue
        turns += 1
        if msg.get("role") == "user" and not first_user:
            first_user = text
            started = entry.get("timestamp") or ""

    if not turns:
        return None  # an empty or aborted session is not a lesson

    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0

    preview = " ".join(first_user.split())
    if len(preview) > 110:
        preview = preview[:107] + "..."

    return Conversation(
        session_id=session_id,
        path=path,
        title=title or (preview[:48] or "Untitled lesson"),
        preview=preview,
        started=started,
        last_active=mtime,
        turns=turns,
    )


def list_conversations(cwd: Path) -> list[Conversation]:
    """Past lessons, newest first."""
    folder = transcript_dir(cwd)
    if not sdk.is_dir(folder):
        return []

    out = []
    for path in folder.glob("*.jsonl"):
        convo = _summarise(path)
        if convo is not None:
            out.append(convo)
    out.sort(key=lambda c: c.last_active, reverse=True)
    return out


def search(conversations: list[Conversation], query: str) -> list[Conversation]:
    """Lessons containing `query`, newest first.

    Title and preview are checked first (cheap); only then is the transcript
    opened. Case-insensitive, plain substring - no regex surprises for someone
    searching for `array[i]`.
    """
    q = query.strip().lower()
    if not q:
        return conversations

    hits = []
    for convo in conversations:
        if q in convo.title.lower() or q in convo.preview.lower():
            hits.append(convo)
            continue
        for msg in read_messages(convo.path):
            if q in msg.text.lower():
                hits.append(convo)
                break
    return hits
