"""
A debug report must be safe to send, and cheap to build on a crash path.

Two separate guarantees, both regression-tested here:

1. **No credential leaves the machine.** The scrub is applied inside
   `build_report_text`, so every path out of the module - the Desktop file and
   the upload - is covered by construction. Unit detail lives in
   `test_report_scrub.py`; this file proves the wiring, on a REAL report built
   from this machine's actual settings.

2. **`lightweight=True` has no side effects.** The crash path offers a report
   four seconds after a launch that followed a dirty exit. The full report
   validates every installed plugin (`exec_module` on each) and opens five
   TCP+TLS sockets, on the UI thread. Doing that inside the crash handler is
   how you crash inside the crash handler.
"""

import socket

import pytest

from techdeck.core import debug_report

SKIPPED_SECTIONS = [
    "PLUGINS (validated on this machine)",
    "IMPORT PROBE",
    "DRAWING READER",
    "NETWORK CONNECTIVITY",
]
ALWAYS_SECTIONS = [
    "SYSTEM / VERSIONS",
    "PREVIOUS SESSION",
    "ENVIRONMENT",
    "USAGE TELEMETRY",
    "PENDING FLOW COMMANDS",
    "SETTINGS SNAPSHOT",
    "HANG / CRASH STACK DUMPS",
    "LOGS",
]


@pytest.fixture(scope="module")
def light_report():
    """One real lightweight build, shared - it reads this machine's logs."""
    return debug_report.build_report_text(None, lightweight=True)


# The real leaked value, signature mangled. It has to be INJECTED: conftest
# redirects %LOCALAPPDATA% for the whole session, so the suite's settings.json
# is empty and a report built from it has no URL in it at all. A test that
# merely greps a sandboxed report for "sig=" passes whatever the code does -
# which is exactly how this leak survived unnoticed in the first place.
LEAKED_URL = (
    "https://REDACTED-ENVIRONMENT.api."
    "powerplatform.com:443/powerautomate/automations/direct/cu/20/workflows/"
    "aaaa1111bbbb2222cccc3333dddd4444/triggers/manual/paths/invoke"
    "?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0"
    "&sig=REDACTED"
)


@pytest.fixture
def leaky_settings(monkeypatch):
    """Plant the leaked settings shape the 2026-10-21 report really had."""
    from techdeck.core import settings as settings_mod

    class FakeSettings:
        data = {
            "plugin_settings": {
                "922_setup": {"webhook_url": LEAKED_URL, "dry_run": False},
                "922_batch_repeater": {"repeat_webhook_url": LEAKED_URL},
            },
            "settings": {"theme": "halloween", "api_usage": {"tokens_used": 437}},
        }

    monkeypatch.setattr(settings_mod, "SettingsManager", FakeSettings)
    return LEAKED_URL


class TestNothingLeaks:
    def test_the_signature_never_reaches_the_report(self, leaky_settings):
        """The 2026-10-21 leak, through the real assembler."""
        joined = "\n".join(debug_report.build_report_text(None, lightweight=True))
        assert "sig=" not in joined
        assert "mangledZZZZsignature" not in joined
        assert "&sv=" not in joined
        assert "&sp=" not in joined

    def test_the_host_survives_so_the_report_is_still_useful(self, leaky_settings):
        """Scrubbing must not blank the whole address - which endpoint was
        configured is the diagnosis the section exists to deliver."""
        joined = "\n".join(debug_report.build_report_text(None, lightweight=True))
        assert "powerplatform.com" in joined
        assert "<query redacted>" in joined

    def test_the_written_file_is_scrubbed_too(self, tmp_path, monkeypatch,
                                              leaky_settings):
        """Guards against a future caller that writes without building."""
        monkeypatch.setattr(debug_report.Path, "home", staticmethod(lambda: tmp_path))
        monkeypatch.setattr(debug_report, "_local_appdata", lambda: tmp_path)
        out = debug_report.generate_debug_report(None, lightweight=True)
        text = out.read_text(encoding="utf-8")
        assert "sig=" not in text
        assert "powerplatform.com" in text

    def test_the_sandboxed_suite_cannot_make_this_vacuous(self, leaky_settings):
        """Meta-guard: prove the fixture really put a secret in the report's
        path, so the assertions above can never silently test nothing."""
        joined = "\n".join(debug_report._collect_settings())
        assert "powerplatform.com" in joined


class TestLightweightIsCheap:
    def test_the_side_effecting_sections_are_skipped(self, light_report):
        joined = "\n".join(light_report)
        for title in SKIPPED_SECTIONS:
            assert title not in joined, f"{title} must not run on a crash path"

    def test_everything_describing_the_failure_is_kept(self, light_report):
        joined = "\n".join(light_report)
        for title in ALWAYS_SECTIONS:
            assert title in joined, f"{title} is how the failure gets diagnosed"

    def test_it_says_so_in_the_report(self, light_report):
        """A maintainer reading a trimmed report must know it was trimmed."""
        assert any("lightweight" in line for line in light_report[:3])

    def test_no_socket_is_opened(self, monkeypatch):
        """The connectivity collector is 5 connects at 4s each."""
        def boom(*a, **k):
            raise AssertionError("lightweight must not open a socket")
        monkeypatch.setattr(socket, "create_connection", boom)
        monkeypatch.setattr(socket, "socket", boom)
        debug_report.build_report_text(None, lightweight=True)

    def test_no_plugin_is_imported(self, monkeypatch):
        called = []
        monkeypatch.setattr(debug_report, "_collect_plugins",
                            lambda: called.append("ran") or [])
        debug_report.build_report_text(None, lightweight=True)
        assert not called

    def test_the_full_report_still_runs_those_sections(self, monkeypatch):
        """The skip must be conditional, not a deletion - the interactive
        Settings button still wants the whole picture."""
        for name in ("_collect_plugins", "_collect_import_probe",
                     "_collect_drawing_reader", "_collect_connectivity"):
            monkeypatch.setattr(debug_report, name, lambda: ["(stubbed)"])
        joined = "\n".join(debug_report.build_report_text(None, lightweight=False))
        for title in SKIPPED_SECTIONS:
            assert title in joined


class TestRedactDoesNotLie:
    def test_a_counter_whose_name_contains_token_is_not_blanked(self):
        """`tokens_used` is a ticket tally. The old key-name-only rule printed
        it as <redacted>, which made the report misreport the state it exists
        to show."""
        out = debug_report._redact({"api_usage": {"tokens_used": 437}})
        assert out["api_usage"]["tokens_used"] == 437

    def test_an_empty_credential_field_stays_visible_as_empty(self):
        """"api_key": "" is a useful fact: nothing is configured."""
        assert debug_report._redact({"api_key": ""})["api_key"] == ""

    def test_a_real_looking_secret_is_blanked(self):
        out = debug_report._redact({"api_key": "sk-live-ABCDEFGHIJKLMNOPQRST"})
        assert out["api_key"] == "<redacted>"

    def test_it_recurses_into_lists_and_dicts(self):
        out = debug_report._redact(
            {"plugins": [{"secret": "ABCDEFGHIJKLMNOPQRSTUVWX", "name": "ok"}]})
        assert out["plugins"][0]["secret"] == "<redacted>"
        assert out["plugins"][0]["name"] == "ok"

    def test_a_webhook_url_is_left_for_the_scrubber(self):
        """_redact must NOT blank it - report_scrub keeps the host and drops
        only the query. Blanking here would throw the host away first."""
        url = "https://x.powerplatform.com/invoke?sig=ABCDEFGHIJKLMNOP"
        out = debug_report._redact({"webhook_url": url})
        assert out["webhook_url"] == url


class TestOutboxSection:
    def test_it_reports_a_depth_per_command(self, tmp_path, monkeypatch):
        from techdeck.core import flow_client
        monkeypatch.setattr(flow_client, "flow_dir", lambda: tmp_path)
        outbox = tmp_path / "outbox"
        outbox.mkdir()
        (outbox / "send_debug_report.jsonl").write_text(
            '{"command": "send_debug_report"}\n{"command": "send_debug_report"}\n',
            encoding="utf-8")
        lines = debug_report._collect_outbox()
        assert any("send_debug_report" in l and "2 waiting" in l for l in lines)

    def test_it_says_so_when_nothing_was_ever_queued(self, tmp_path, monkeypatch):
        from techdeck.core import flow_client
        monkeypatch.setattr(flow_client, "flow_dir", lambda: tmp_path)
        assert "Nothing has ever been queued" in "\n".join(debug_report._collect_outbox())

    def test_parked_commands_are_reported_loudly(self, tmp_path, monkeypatch):
        """A parked command is already lost unless someone looks, and a
        non-zero count here almost always means a build shipped with the flow
        URL unset - which silently eats every submission on that machine."""
        from techdeck.core import flow_client
        monkeypatch.setattr(flow_client, "flow_dir", lambda: tmp_path)
        dead = tmp_path / "dead_letter"
        dead.mkdir()
        (dead / "suggestion_create.jsonl").write_text(
            '{"command": "suggestion_create"}\n', encoding="utf-8")
        joined = "\n".join(debug_report._collect_outbox())
        assert "UNDELIVERABLE" in joined
        assert "suggestion_create" in joined
        assert "1 parked" in joined
