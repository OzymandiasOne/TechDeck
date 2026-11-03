"""
The debug report must not carry credentials.

These tests exist because of a real leak found 2026-10-21: the settings keys
`webhook_url` and `repeat_webhook_url` matched none of the old key-name markers
("api_key", "token", "password", "secret"), so every debug report on every
machine contained the live Power Automate trigger URLs - signature included -
in plaintext. The two fixtures below are the ACTUAL lines from the report found
on the maintainer's Desktop, with the signature characters mangled.

The guards are as important as the redactions: the old key-name approach also
blanked `"tokens_used": 0`, a ticket counter, which made the report lie about
the thing it was supposed to diagnose.
"""

import pytest

from techdeck.core.report_scrub import (
    REDACTED_QUERY,
    REDACTED_VALUE,
    scrub_line,
    scrub_text,
)

# The real leaked lines (signature + workflow id characters mangled).
LEAKED_WEBHOOK = (
    '    "webhook_url": "https://defaultc102274db9ed4a418ee7a0f5e932ca.98.'
    'environment.api.powerplatform.com:443/powerautomate/automations/direct/'
    'cu/20/workflows/aaaa1111bbbb2222cccc3333dddd4444/triggers/manual/paths/'
    'invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0'
    '&sig=REDACTED",'
)
LEAKED_REPEAT = LEAKED_WEBHOOK.replace('"webhook_url"', '"repeat_webhook_url"')


class TestTheRealLeak:
    @pytest.mark.parametrize("line", [LEAKED_WEBHOOK, LEAKED_REPEAT])
    def test_the_signature_does_not_survive(self, line):
        out = scrub_line(line)
        assert "sig=" not in out
        assert "mangledZZZZsignature" not in out
        assert "sp=" not in out
        assert "sv=" not in out

    @pytest.mark.parametrize("line", [LEAKED_WEBHOOK, LEAKED_REPEAT])
    def test_the_host_is_kept_because_that_is_the_diagnosis(self, line):
        """The host is not the secret; it is the answer to "what was it
        talking to". Blanking the whole value would make the report useless."""
        out = scrub_line(line)
        assert "powerplatform.com" in out
        assert "/triggers/manual/paths/invoke" in out
        assert REDACTED_QUERY in out

    def test_the_line_still_looks_like_json(self):
        """The settings snapshot is parsed by eye; a scrub that breaks the
        shape costs the reader more than it saves."""
        out = scrub_line(LEAKED_WEBHOOK)
        assert out.startswith('    "webhook_url": "')
        assert out.rstrip().endswith('",')


class TestTheClassNotJustTheInstance:
    def test_a_bare_url_in_a_log_line_is_scrubbed_too(self):
        """No dictionary key at all - this is why the rule works on text.
        A plugin that logs its own webhook URL leaks exactly the same secret."""
        line = ("2026-10-21 09:14:02 INFO POST https://x.powerplatform.com/"
                "invoke?api-version=1&sig=SECRETSECRETSECRET failed")
        out = scrub_line(line)
        assert "sig=" not in out
        assert "SECRETSECRETSECRET" not in out
        assert "https://x.powerplatform.com/invoke" in out

    def test_a_url_under_an_unexpected_key_name_is_scrubbed(self):
        line = '    "some_future_endpoint": "https://h.example.com/go?sig=ABCDEFGHIJKLMNOP",'
        assert "sig=" not in scrub_line(line)

    def test_two_urls_on_one_line(self):
        line = ("from https://a.example.com/x?sig=AAAAAAAAAAAAAAAA "
                "to https://b.example.com/y?sig=BBBBBBBBBBBBBBBB")
        out = scrub_line(line)
        assert "sig=" not in out
        assert "a.example.com" in out and "b.example.com" in out


class TestWhatMustNotBeTouched:
    def test_a_url_with_no_query_is_left_alone(self):
        """The updater's manifest address and a Release link are diagnostic
        facts, not secrets."""
        line = "  manifest: https://ozymandiasone.github.io/TechDeck-updates/manifest.json"
        assert scrub_line(line) == line

    def test_a_ticket_counter_is_not_a_credential(self):
        """The old key-name markers blanked this, because the key contains
        "token". It is a tally."""
        line = '      "tokens_used": 0,'
        assert scrub_line(line) == line

    def test_a_short_value_under_a_matching_key_survives(self):
        line = '    "api_key": "",'
        assert scrub_line(line) == line

    def test_ordinary_settings_are_untouched(self):
        for line in (
            '    "theme": "halloween",',
            '    "base_path": "C:\\\\Users\\\\someone\\\\OneDrive - Company\\\\922 QTDR",',
            '    "tickets": 4365,',
            '    "dry_run": false,',
            "  [OK] openpyxl                        3.1.5",
            "Computer / user:  LAPTOP-VI327KUH / someone",
        ):
            assert scrub_line(line) == line, line

    def test_prose_under_a_matching_key_is_not_blanked(self):
        """A long sentence is not a token, even under a key called "secret"."""
        line = '  secret_note: the batch was reused from last month on purpose'
        assert scrub_line(line) == line


class TestNonUrlSecrets:
    def test_a_long_opaque_value_under_a_credential_key_is_blanked(self):
        line = '    "access_key": "AKIAIOSFODNN7EXAMPLEEXAMPLE",'
        out = scrub_line(line)
        assert "AKIAIOSFODNN7EXAMPLE" not in out
        assert REDACTED_VALUE in out

    def test_the_plain_form_works_too(self):
        line = "  bearer_token = eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        out = scrub_line(line)
        assert "eyJhbGciOi" not in out
        assert REDACTED_VALUE in out


class TestTheWholeReport:
    def test_scrub_text_handles_a_mixed_report(self):
        report = [
            "TechDeck Debug Report",
            "",
            "=== SETTINGS SNAPSHOT " + "=" * 42,
            LEAKED_WEBHOOK,
            LEAKED_REPEAT,
            '    "theme": "halloween",',
            "=== END OF REPORT " + "=" * 46,
        ]
        out = scrub_text(report)
        assert len(out) == len(report)
        joined = "\n".join(out)
        assert "sig=" not in joined
        assert "halloween" in joined
        assert out[0] == "TechDeck Debug Report"

    def test_scrubbing_is_idempotent(self):
        """Belt and braces: the assembler may grow a second scrub pass, and a
        double-scrubbed report must not degrade."""
        once = scrub_text([LEAKED_WEBHOOK, LEAKED_REPEAT])
        twice = scrub_text(once)
        assert twice == once

    def test_empty_and_odd_input_never_raises(self):
        assert scrub_text([]) == []
        assert scrub_text(["", "   ", "?", "https://", "=", '":"']) is not None

    def test_a_report_is_never_dropped_for_being_unscrubbable(self):
        """scrub_text must return a line for every line in, so no section can
        silently vanish from a report."""
        lines = [f"line {i}" for i in range(50)]
        assert len(scrub_text(lines)) == 50
