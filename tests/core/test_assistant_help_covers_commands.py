"""Every Assistant command must be findable in /help.

**The trap.** A command is three edits: a `_cmd_*` method, an entry in
`AssistantBrain._handlers`, and a line in `HELP_TEXT`. The first two are what
make it work, so the third is the one that gets forgotten - and nothing
complains, because a command missing from /help works perfectly for anybody who
already knows it exists.

Four shipped that way on 2026-10-13: `/step`, `/steps`, `/waiting` and `/help`
itself. The person who asked for steps and waiting-on would have typed `/help`
to find them and seen neither. `docs/ASSISTANT.md` listed all four, which is
worse, not better - the doc nobody opens was ahead of the help everybody does.

Aliases are fine: a handler is covered when ANY of its names is in the help.
"""

from __future__ import annotations

import pytest

from techdeck.core.assistant.commands import HELP_TEXT, AssistantBrain
from techdeck.core.assistant.store import AssistantStore


@pytest.fixture
def brain(tmp_path):
    return AssistantBrain(AssistantStore(tmp_path / "assistant.json"))


def _named_in_help(name: str) -> bool:
    """`/name` as a whole word - `/step` must not be matched by `/steps`."""
    needle = f"/{name}"
    start = 0
    while True:
        at = HELP_TEXT.find(needle, start)
        if at < 0:
            return False
        after = at + len(needle)
        if after >= len(HELP_TEXT) or not HELP_TEXT[after].isalnum():
            return True
        start = after


def test_every_command_has_a_line_in_help(brain):
    by_handler: dict = {}
    for name, handler in brain._handlers().items():
        by_handler.setdefault(handler, []).append(name)

    missing = sorted("/" + sorted(names)[0]
                     for names in by_handler.values()
                     if not any(_named_in_help(n) for n in names))

    assert not missing, (
        "These commands work but are not in /help, so the only way to find "
        "them is to already know they exist:\n  " + "\n  ".join(missing)
        + "\n\nAdd a line to HELP_TEXT in techdeck/core/assistant/commands.py.")


def test_help_does_not_advertise_a_command_that_does_not_exist(brain):
    """The other direction: a renamed command leaves a dead line behind."""
    import re

    known = set(brain._handlers())
    advertised = set(re.findall(r"/([a-z?]+)", HELP_TEXT))
    # Grammar examples in the footer are not commands.
    dead = sorted(advertised - known)
    assert not dead, (
        f"/help names commands that no longer exist: {dead}")


def test_the_four_that_shipped_missing_are_covered(brain):
    """A named regression guard, so the story stays attached to the names."""
    for name in ("step", "steps", "waiting", "help"):
        assert _named_in_help(name), f"/{name} fell out of HELP_TEXT again"
