"""
Debug-report scrubbing
======================
Strips credentials out of an assembled debug report, line by line, as the very
last step before the text is written or sent.

WHY THIS EXISTS (2026-10-21). `debug_report._redact` blanks dictionary values
whose KEY looks like a credential, and its marker list was
`("api_key", "token", "password", "secret")`. Two live settings keys are called
`webhook_url` and `repeat_webhook_url`, which match none of those - so every
debug report ever generated carried the full Power Automate trigger URLs,
including the `sig=` SAS signature that IS the bearer credential for those
flows, in plaintext. Found while planning the auto-send feature: reports were
hand-carried over Teams until now, but uploading one to a cloud store would
have widened that exposure considerably.

The fix is deliberately NOT a longer marker list. A key-name allowlist can only
catch the names someone thought of, and the same mistake was already made once.
So this module works on the TEXT, not the structure:

  1. Any URL carrying a query string keeps its host and path and loses the
     query. That one rule kills the whole class - every flow address, present
     and future, under any key name, in any section, including free-text log
     lines where no dictionary key exists at all.
  2. A `key: value` or `key=value` pair whose key looks credential-ish AND
     whose value is secret-shaped is blanked. This is the backstop for a secret
     that is not a URL.

Rule 1 keeps the host on purpose: "it was talking to
defaultc1022...powerplatform.com" is exactly the diagnosis a report exists to
deliver, and the host is not the secret - the signature is. A bare URL with no
query (the updater's manifest address, a GitHub Release link) is untouched for
the same reason.

Pure text in, pure text out: no app imports, no I/O, so it is trivially
testable and cannot fail the report.
"""

import re
from typing import List, Sequence

__all__ = ["scrub_text", "scrub_line", "REDACTED_QUERY", "REDACTED_VALUE"]

REDACTED_QUERY = "<query redacted>"
REDACTED_VALUE = "<redacted>"

# A URL, stopping at whitespace and at the characters that normally close one
# in JSON, prose or a log line. The trailing-punctuation strip below handles
# the rest, so a URL at the end of a sentence keeps its full path.
_URL_RE = re.compile(r"""https?://[^\s"'<>\\]+""", re.IGNORECASE)

# Punctuation that is almost certainly sentence/JSON structure rather than part
# of the address. Stripped from the right before we decide where the query ends.
_URL_TRAILING = ",;)]}\"'.>"

# Key names that may carry a secret. `url` is deliberately ABSENT: a plain
# download_url is useful diagnostic information and rule 1 already removes the
# dangerous half of any address. `webhook` covers the keys that actually leaked.
_SECRET_KEY_RE = re.compile(
    r"(?i)(webhook|signature|\bsig\b|\bsas\b|secret|password|passwd"
    r"|token|api[_-]?key|access[_-]?key|\bkey\b|credential|bearer)"
)

# `"key": "value"` (JSON, as the settings snapshot prints it) and `key = value`
# / `key: value` (prose and log lines).
_JSON_PAIR_RE = re.compile(r'^(?P<head>\s*"(?P<key>[^"]+)"\s*:\s*")(?P<value>.*)(?P<tail>"\s*,?\s*)$')
_PLAIN_PAIR_RE = re.compile(r'^(?P<head>\s*(?P<key>[A-Za-z0-9_.\-]+)\s*[:=]\s*)(?P<value>\S.*?)(?P<tail>\s*)$')

# How long a value has to be before we treat it as possibly-secret. Short
# values are counters and flags: `"tokens_used": 0` is a ticket tally, not a
# credential, and blanking it made the old report actively misleading.
_SECRET_MIN_LEN = 16


def _looks_secret(value: str) -> bool:
    """A value long enough and dense enough to be a credential rather than a
    word, a number, a path fragment or a boolean."""
    v = value.strip().strip('"')
    if len(v) < _SECRET_MIN_LEN:
        return False
    if " " in v:                      # prose, not a token
        return False
    # Already handled. A URL whose query we just removed must NOT then be
    # blanked whole by the key-name rule - keeping the host is the entire
    # point of rule 1, and `webhook_url` matches the key pattern.
    if REDACTED_QUERY in v or REDACTED_VALUE in v:
        return False
    return True


def _scrub_urls(line: str) -> str:
    """Replace every URL query string on the line with a marker."""
    def repl(match: "re.Match[str]") -> str:
        url = match.group(0)
        # Peel structural punctuation off the right so it survives untouched.
        trailing = ""
        while url and url[-1] in _URL_TRAILING:
            trailing = url[-1] + trailing
            url = url[:-1]
        base, _sep, query = url.partition("?")
        # No query, or nothing left in it: nothing to redact. The empty case
        # matters - the marker starts with "<", which the URL pattern stops
        # at, so an already-scrubbed address arrives here as "...invoke?" and
        # would otherwise collect a second marker on every pass.
        if not query:
            return url + trailing
        return f"{base}?{REDACTED_QUERY}{trailing}"
    return _URL_RE.sub(repl, line)


def _scrub_pair(line: str) -> str:
    """Blank a credential-ish key's value, JSON or plain form."""
    for pattern in (_JSON_PAIR_RE, _PLAIN_PAIR_RE):
        m = pattern.match(line)
        if not m:
            continue
        if not _SECRET_KEY_RE.search(m.group("key")):
            return line
        if not _looks_secret(m.group("value")):
            return line
        return f"{m.group('head')}{REDACTED_VALUE}{m.group('tail')}"
    return line


def scrub_line(line: str) -> str:
    """Scrub one line. URLs first, so a redacted address is never then
    mistaken for a secret-shaped value and blanked wholesale - the host is
    the part worth keeping."""
    return _scrub_pair(_scrub_urls(line))


def scrub_text(lines: Sequence[str]) -> List[str]:
    """Scrub an assembled report. Never raises: a report that cannot be
    scrubbed must still be written, but it must be written SAFE, so a line
    that somehow explodes is replaced rather than passed through."""
    out: List[str] = []
    for line in lines:
        try:
            out.append(scrub_line(line))
        except Exception:                                  # pragma: no cover
            out.append("<line omitted: could not be scrubbed safely>")
    return out
