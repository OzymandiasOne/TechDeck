"""
Java Tutor - the engine.

Wraps the Claude Code CLI in a QProcess and turns its newline-delimited JSON
stream into Qt signals. EVERY assumption about how the CLI behaves lives in
this file and nowhere else, so a CLI update breaks one module instead of the
app - and swapping to the Anthropic API later means rewriting only this file.

Why one process per turn instead of one long-lived process:
    Each turn is atomic. If a turn dies, the conversation survives - the CLI
    already persisted it, and the next turn passes `--resume <session_id>`.
    It also makes "continue an old lesson from the history sidebar" free:
    resuming a three-week-old session is the same code path as continuing the
    current one. Measured cost is ~1.7s to first word including process
    startup, which is fine for a chat.

SAFETY - the tutor must never write his code:
    The whole point of the tutoring setup is that HE types the Java. So the
    CLI is launched with an explicit deny list (see _DENIED_TOOLS) that strips
    Write, Edit and every command runner. Verified: with these flags the init
    event reports no Write/Edit, and a direct "create a file" instruction is
    refused.

    `--restricted` looks like the right flag for this and is NOT usable: it
    also drops the java-tutor skill and CLAUDE.md, which are the entire reason
    for driving the CLI instead of calling the API. Verified 2026-09-01.

    Because a deny list goes stale when the CLI adds tools, `sandbox_warning`
    fires if the session ever reports a tool outside _ALLOWED_TOOLS. The app
    surfaces it rather than trusting the flags silently.
"""

import codecs
import json
import logging
import os
import shutil
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

# Long-path-safe filesystem checks (Hard Rule 14). A raw .is_dir() answers
# False for a folder that exists once the path passes 260 characters.
try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:  # standalone / headless testing
    import sys as _sys
    import pathlib as _pl
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk

logger = logging.getLogger(__name__)


# The working directory the tutor runs in. Sets which CLAUDE.md loads, which
# files it can read, and which folder its transcripts are filed under.
TUTOR_CWD = Path(r"C:\Dev\Code Tutor")

# Read-only tools the tutor is allowed to keep. Skill must stay - it is how
# java-tutor fires.
_ALLOWED_TOOLS = {"Read", "Glob", "Grep", "Skill"}

# Everything else, denied explicitly. Unknown names are harmless, so err on the
# side of listing more.
#
# This list cannot be built by watching one session: Claude Code DEFERS some
# tools, so they are absent from the init event until something loads them.
# `Monitor` was missed exactly that way and turned up in the first real session
# (2026-09-02). Hence the self-healing below - the static list is the fast path,
# not the guarantee.
_DENIED_TOOLS = [
    "Write", "Edit", "NotebookEdit",
    "Bash", "PowerShell", "BashOutput", "KillShell",
    "Task", "Workflow", "TaskOutput", "TaskStop",
    "WebFetch", "WebSearch",
    "CronCreate", "CronDelete", "CronList",
    "DesignSync", "EnterWorktree", "ExitWorktree",
    "EnterPlanMode", "ExitPlanMode",
    "ListAgents", "SendMessage", "SendUserFile", "RemoteTrigger",
    "PushNotification", "Monitor",
    "ScheduleWakeup", "ReportFindings", "ToolSearch", "LSP",
    "Artifact", "AskUserQuestion", "SendFeedback", "EndConversation",
]


class ClaudeUnavailable(RuntimeError):
    """Raised when the Claude Code CLI cannot be located on this machine."""


def find_claude() -> str:
    """Absolute path to the `claude` executable.

    PATH is searched first, then the known WinGet install location - the
    frozen exe does not necessarily inherit the shell's PATH.
    """
    found = shutil.which("claude")
    if found:
        return found

    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        pkgs = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if sdk.is_dir(pkgs):
            for pattern in ("Anthropic.ClaudeCode*/claude.exe",
                            "Anthropic.ClaudeCode*/claude.cmd",
                            "Anthropic.ClaudeCode*/claude"):
                for hit in pkgs.glob(pattern):
                    return str(hit)

    raise ClaudeUnavailable(
        "Claude Code is not installed on this machine, or is not on PATH.\n\n"
        "The Java Tutor runs on the Claude Code CLI. Install it, or open a "
        "terminal and check that typing `claude` works."
    )


class ClaudeSession(QObject):
    """One tutoring conversation, driven turn by turn.

    Signals:
        turn_started()                  a turn is now in flight
        delta(str)                      a chunk of assistant text arrived
        tool_started(str)               the tutor started using a tool
        turn_finished(str)              turn ended cleanly; arg is the full text
        turn_failed(str)                turn ended badly; arg is a plain message
        session_ready(str)              the CLI reported this turn's session id
        rate_limit(dict)                usage-window info, straight from the CLI
        sandbox_warning(list)           unexpected tools present in the session
    """

    turn_started = Signal()
    delta = Signal(str)
    tool_started = Signal(str)
    turn_finished = Signal(str)
    turn_failed = Signal(str)
    session_ready = Signal(str)
    rate_limit = Signal(dict)
    sandbox_warning = Signal(list)

    def __init__(self, parent=None, cwd: Path = TUTOR_CWD):
        super().__init__(parent)
        self._cwd = Path(cwd)
        self._proc: QProcess | None = None
        self._buf = ""            # partial trailing LINE between reads
        # A read can also split a multi-byte UTF-8 character in half; an
        # incremental decoder holds the partial bytes instead of emitting
        # U+FFFD for each half (observed on an em-dash, 2026-09-01).
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._text_parts: list[str] = []
        self._stderr = ""
        self._session_id: str | None = None
        self._interrupted = False
        # Tools seen in a session that _DENIED_TOOLS did not know about.
        # Added to the deny list for every later turn (see _check_sandbox).
        self._extra_denied: list[str] = []

    # -- state -------------------------------------------------------------

    @property
    def session_id(self) -> str | None:
        """Id of the conversation, once the CLI has reported one."""
        return self._session_id

    @property
    def busy(self) -> bool:
        return self._proc is not None

    def adopt_session(self, session_id: str) -> None:
        """Continue an existing conversation (e.g. one picked in history)."""
        if self.busy:
            raise RuntimeError("cannot switch conversation mid-turn")
        self._session_id = session_id or None

    def reset(self) -> None:
        """Start a brand new conversation on the next turn."""
        if self.busy:
            raise RuntimeError("cannot reset mid-turn")
        self._session_id = None

    # -- driving a turn ----------------------------------------------------

    def send(self, message: str) -> None:
        """Send one user message. Emits `delta` as the answer streams back."""
        if self.busy:
            raise RuntimeError("a turn is already running")
        if not message.strip():
            return

        exe = find_claude()

        args = [
            "-p",
            "--output-format", "stream-json",
            "--include-partial-messages",
            "--verbose",              # required for stream-json on -p
            "--strict-mcp-config",    # no Gmail/etc. in a tutoring session
        ]
        if self._session_id:
            args += ["--resume", self._session_id]
        # --allowedTools AUTO-APPROVES; it does not restrict. Without it the
        # read tools are denied outright, because -p has nobody to ask.
        args += ["--allowedTools"] + sorted(_ALLOWED_TOOLS)
        # --disallowedTools is what actually removes a tool from the session.
        args += ["--disallowedTools"] + _DENIED_TOOLS + self._extra_denied

        self._buf = ""
        self._decoder.reset()
        self._text_parts = []
        self._stderr = ""
        self._interrupted = False

        proc = QProcess(self)
        proc.setProgram(exe)
        proc.setArguments(args)
        proc.setWorkingDirectory(str(self._cwd))
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        proc.readyReadStandardOutput.connect(self._on_stdout)
        proc.readyReadStandardError.connect(self._on_stderr)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_proc_error)

        self._proc = proc
        self.turn_started.emit()

        logger.info("java_tutor: starting turn (resume=%s)", self._session_id)
        proc.start()
        if not proc.waitForStarted(10000):
            self._proc = None
            self.turn_failed.emit("Could not start Claude Code.")
            return

        # The prompt goes over stdin, not argv: pasted Java blows past the
        # Windows command-line limit and would need shell-quoting besides.
        proc.write(message.encode("utf-8"))
        proc.closeWriteChannel()

    def interrupt(self) -> None:
        """Stop the turn in progress. The conversation itself survives."""
        if not self._proc:
            return
        self._interrupted = True
        self._proc.kill()

    # -- stream parsing ----------------------------------------------------

    def _on_stdout(self) -> None:
        if not self._proc:
            return
        chunk = self._decoder.decode(self._proc.readAllStandardOutput().data())
        self._buf += chunk

        # The CLI writes one JSON object per line, but a read can land
        # mid-line - keep the tail for next time.
        *lines, self._buf = self._buf.split("\n")
        for line in lines:
            line = line.strip()
            if line:
                self._handle_event(line)

    def _on_stderr(self) -> None:
        if not self._proc:
            return
        self._stderr += self._proc.readAllStandardError().data().decode("utf-8", "replace")

    def _handle_event(self, line: str) -> None:
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("java_tutor: non-JSON line ignored: %.120s", line)
            return

        kind = evt.get("type")

        if kind == "system" and evt.get("subtype") == "init":
            sid = evt.get("session_id")
            if sid and sid != self._session_id:
                self._session_id = sid
                self.session_ready.emit(sid)
            self._check_sandbox(evt.get("tools") or [])

        elif kind == "stream_event":
            inner = evt.get("event") or {}
            if inner.get("type") == "content_block_delta":
                d = inner.get("delta") or {}
                if d.get("type") == "text_delta":
                    text = d.get("text") or ""
                    if text:
                        self._text_parts.append(text)
                        self.delta.emit(text)
            elif inner.get("type") == "content_block_start":
                block = inner.get("content_block") or {}
                if block.get("type") == "tool_use":
                    self.tool_started.emit(block.get("name") or "tool")

        elif kind == "rate_limit_event":
            info = evt.get("rate_limit_info") or {}
            if info:
                self.rate_limit.emit(info)

        elif kind == "result":
            # `result` carries the authoritative final text. Prefer it over the
            # accumulated deltas, which can miss a block the stream skipped.
            if evt.get("is_error"):
                msg = str(evt.get("result") or "The tutor hit an error.")
                self._fail(msg)
            else:
                final = evt.get("result")
                if isinstance(final, str) and final.strip():
                    self._text_parts = [final]

    def _check_sandbox(self, tools: list) -> None:
        """Deny anything the allowlist does not name, from the next turn on.

        The deny list is a blocklist, so a tool the CLI defers or newly ships
        arrives un-denied. Rather than just warn and hope someone reads it,
        add it to `_extra_denied` - the allowlist is the real policy, so
        anything outside it is unwanted by definition. An unknown tool can
        therefore be present for at most one turn.
        """
        unexpected = sorted(set(tools) - _ALLOWED_TOOLS - set(self._extra_denied))
        if not unexpected:
            return
        self._extra_denied.extend(unexpected)
        logger.warning("java_tutor: denying unexpected tools from next turn: %s", unexpected)
        self.sandbox_warning.emit(unexpected)

    # -- teardown ----------------------------------------------------------

    def _on_proc_error(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self._fail("Could not start Claude Code. Is it still installed?")

    def _on_finished(self, exit_code: int, _status=None) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            proc.deleteLater()

        # Flush a final line with no trailing newline.
        tail = self._buf.strip()
        self._buf = ""
        if tail:
            self._handle_event(tail)

        if self._interrupted:
            self.turn_finished.emit("".join(self._text_parts))
            return

        if exit_code != 0 and not self._text_parts:
            detail = self._stderr.strip().splitlines()
            hint = detail[-1] if detail else f"exit code {exit_code}"
            self._fail(f"The tutor stopped unexpectedly ({hint}).")
            return

        self.turn_finished.emit("".join(self._text_parts))

    def _fail(self, message: str) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            proc.kill()
            proc.deleteLater()
        self.turn_failed.emit(message)
