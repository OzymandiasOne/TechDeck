"""Test-session guardrails.

**The test suite must never write into the real %LOCALAPPDATA%\\TechDeck.**
That directory is live USER data on a developer's own machine — the settings
document, the posted-card ledger, and the webhook dry-run previews all live
there — and a test run silently overwriting any of it is data loss that looks
like nothing at all.

Caught 2026-08-10: the 911 Teams Cards dry-run test does not stub
`sdk.write_payload_preview`, so every `pytest` run stamped its FIXTURE payload
(`BATCH: V092 - NEST: 503836`) over the real `last_911_setup_payload.json`.
Harmless in itself — a preview is scratch — but the same path is how
`_ledger_path()` and `SettingsManager` resolve, so the next test that forgets
to patch one of those would quietly rewrite a real ledger or real settings
instead. Individual tests had been patching `_ledger_path` one at a time;
that is a convention, and conventions get forgotten.

A second instance of the same class, found the same day from a colleague's
debug report: `tests/ui/test_run_controller.py` drives the ghost-tile drop
path with a fixture tile literally named `ghost`, and `get_run_logger()`
resolves the SAME way — so every `pytest` run appended
"Dropped 1 selected tile(s) not in the current kit: ghost" to the real
`logs/plugin_runs.log`. 194 lines, 20% of the log, in a file whose entire
purpose is diagnosing colleague-reported failures after the fact.

All four consumers — the preview file, the posted-card ledger, the settings
document and the run/detail logs — resolve their base from
`os.environ["LOCALAPPDATA"]`, so redirecting that one variable for the whole
session closes the class rather than the instances.
"""



import pytest
from _pytest.monkeypatch import MonkeyPatch


@pytest.fixture(scope="session", autouse=True)
def _isolate_localappdata(tmp_path_factory):
    """Point %LOCALAPPDATA% at a throwaway dir for the entire test session."""
    mp = MonkeyPatch()
    fake = tmp_path_factory.mktemp("localappdata")
    mp.setenv("LOCALAPPDATA", str(fake))
    # APPDATA too: same class of user-data root, and cheap to cover.
    mp.setenv("APPDATA", str(fake))
    yield fake
    mp.undo()
