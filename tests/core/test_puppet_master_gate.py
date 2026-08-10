"""The Puppet Master must not reach colleagues before the Halloween release.

He is finished and merged on `main` — face, summon animations, 2501 voice,
/help delivery — spread across ~20 commits that later console work sits on top
of, so reverting was never an option. He ships DORMANT instead, behind
`constants.PUPPET_MASTER_ENABLED`.

These tests are the safety net for a decision that is easy to get wrong twice:
leaking him early (the release is spoiled) or gating him so hard that flipping
the flag at Halloween doesn't actually wake him (the release is broken and
nobody finds out until the day). So every test asserts BOTH states.

His only three entry points:
  1. the console's startup greeting + its "redefine" summon link
  2. the /puppetmaster command
  3. the techdeck://cat/summon link route

Nothing else can reach him: ConsoleCat is a lazy singleton created only by
those paths, and active_cat() returns None until one runs — so the free-text
routing and the /help takeover stay dormant on their own.
"""

import pytest

from techdeck.core import constants


@pytest.fixture
def gate(monkeypatch):
    """Set the flag either way, with the env override cleared so the constant
    is what actually decides."""
    def _set(enabled):
        monkeypatch.delenv("TECHDECK_PUPPET_MASTER", raising=False)
        monkeypatch.setattr(constants, "PUPPET_MASTER_ENABLED", enabled)
    return _set


# ── the flag itself ─────────────────────────────────────────────────────────
def test_he_ships_off():
    """The whole point. If this ever fails on main, a release leaks him."""
    assert constants.PUPPET_MASTER_ENABLED is False


def test_the_env_override_wakes_him_for_local_testing(monkeypatch):
    monkeypatch.setattr(constants, "PUPPET_MASTER_ENABLED", False)
    monkeypatch.setenv("TECHDECK_PUPPET_MASTER", "1")
    assert constants.puppet_master_enabled() is True


def test_the_env_override_can_also_force_him_off(monkeypatch):
    monkeypatch.setattr(constants, "PUPPET_MASTER_ENABLED", True)
    monkeypatch.setenv("TECHDECK_PUPPET_MASTER", "0")
    assert constants.puppet_master_enabled() is False


@pytest.mark.parametrize("junk", ["", "   "])
def test_a_blank_override_defers_to_the_constant(monkeypatch, junk):
    monkeypatch.setattr(constants, "PUPPET_MASTER_ENABLED", False)
    monkeypatch.setenv("TECHDECK_PUPPET_MASTER", junk)
    assert constants.puppet_master_enabled() is False


# ── entry point 1: the startup greeting ─────────────────────────────────────
# Asserted against the SOURCE rather than a live widget: constructing the real
# console needs a QApplication and pulls in the whole theme stack, and what
# matters here is only which branch the greeting takes.

def _greeting_branch_source():
    from pathlib import Path
    src = (Path(constants.__file__).resolve().parents[2]
           / "techdeck" / "ui" / "widgets" / "console.py").read_text(
        encoding="utf-8")
    start = src.index("# Initial message.")
    return src[start:start + 900]


def test_the_startup_greeting_is_gated():
    branch = _greeting_branch_source()
    assert "_puppet_master_live()" in branch, (
        "the startup greeting no longer consults the gate — he would announce "
        "himself to every colleague on launch")
    assert "TechDeck online. Type /help for available commands." in branch


def test_the_summon_link_is_only_authored_when_he_is_live():
    """The 'redefine' anchor must sit in the gated branch, never the plain
    greeting — an unclickable-but-present link would still give him away."""
    # Comments in this region legitimately NAME the url while explaining the
    # gate; only emitted code counts, so drop comment text first.
    code = "\n".join(line.split("#")[0]
                     for line in _greeting_branch_source().splitlines())
    plain, sep, themed = code.partition("else:")
    assert sep, "the greeting is no longer an if/else — re-check this test"
    assert "techdeck://cat/summon" not in plain
    assert "techdeck://cat/summon" in themed


def test_an_import_failure_hides_him_rather_than_leaking_him():
    """The gate helper swallows errors — assert it fails CLOSED."""
    from pathlib import Path
    src = (Path(constants.__file__).resolve().parents[2]
           / "techdeck" / "ui" / "widgets" / "console.py").read_text(
        encoding="utf-8")
    body = src[src.index("def _puppet_master_live"):][:400]
    assert "except Exception:" in body
    assert "return False" in body.split("except Exception:")[1]


# ── entry point 2: the /puppetmaster command ────────────────────────────────
class _Console:
    def __init__(self):
        self.errors, self.system = [], []

    def append_error(self, msg):
        self.errors.append(msg)

    def append_system(self, msg):
        self.system.append(msg)


def _handler(monkeypatch):
    """A CommandHandler with __init__ bypassed — it builds Qt state we don't
    need; only the command map and the dispatch guard are under test."""
    from techdeck.core.command_handler import CommandHandler
    h = CommandHandler.__new__(CommandHandler)
    h.console = _Console()
    h._admin_mode = False
    h._cat = None
    summoned = []
    h._cmd_puppetmaster = lambda args: summoned.append("cmd")
    h.commands = {"/puppetmaster": h._cmd_puppetmaster,
                  "/help": lambda args: None}
    return h, summoned


def test_the_command_reads_as_a_typo_while_he_is_held(gate, monkeypatch):
    gate(False)
    h, summoned = _handler(monkeypatch)
    h.handle_command("/puppetmaster")
    assert summoned == []
    assert h.console.errors == ["Unknown command: /puppetmaster"]
    assert h.console.system == ["Type /help for available commands."]


def test_the_command_works_the_moment_the_flag_flips(gate, monkeypatch):
    gate(True)
    h, summoned = _handler(monkeypatch)
    h.handle_command("/puppetmaster")
    assert summoned == ["cmd"], "flipping the flag did not wake him"
    assert h.console.errors == []


def test_gating_him_did_not_break_every_other_command(gate, monkeypatch):
    gate(False)
    h, _ = _handler(monkeypatch)
    h.handle_command("/help")
    assert h.console.errors == []


def test_he_is_absent_from_help_in_both_states():
    """He was always meant to be undiscoverable — 'those who know, know'."""
    from pathlib import Path
    src = (Path(constants.__file__).resolve().parents[2]
           / "techdeck" / "core" / "command_handler.py").read_text(
        encoding="utf-8")
    help_text = src[src.index("def _cmd_help"):][:2500]
    assert "/puppetmaster" not in help_text


# ── entry point 3: the techdeck://cat/summon link route ─────────────────────
def _link_handler(gate_value, monkeypatch):
    from techdeck.core import command_handler as ch
    from techdeck.core.command_handler import CommandHandler
    monkeypatch.setattr(ch, "puppet_master_enabled", lambda: gate_value)
    h = CommandHandler.__new__(CommandHandler)
    h.console = _Console()
    h._cat = None
    summoned = []

    class _Cat:
        def summon(self, mode):
            summoned.append(mode)

    h._console_cat = lambda: _Cat()
    return h, summoned


def test_a_stale_summon_link_does_nothing_while_he_is_held(monkeypatch):
    """A console open across a flag flip could still hold the old anchor."""
    h, summoned = _link_handler(False, monkeypatch)
    h.handle_internal_link("techdeck://cat/summon")
    assert summoned == []
    assert h.console.errors == [], "a silent no-op, not a visible error"


def test_the_summon_link_materializes_him_once_live(monkeypatch):
    h, summoned = _link_handler(True, monkeypatch)
    h.handle_internal_link("techdeck://cat/summon")
    assert summoned == ["materialize"]


def test_unrelated_links_still_report_themselves_broken(monkeypatch):
    h, _ = _link_handler(False, monkeypatch)
    h.handle_internal_link("techdeck://nonsense/xyz")
    assert h.console.errors and "Unroutable" in h.console.errors[0]
