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



from pathlib import Path

import pytest
from _pytest.monkeypatch import MonkeyPatch

ROOT = Path(__file__).resolve().parents[1]


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


@pytest.fixture
def private_doc():
    """Resolve a repo path that PUBLISHING STRIPS - or skip the test.

    `tools/publish_mirror.py` deletes CLAUDE.md, LESSONS_LEARNED.md, docs/,
    .claude/ and friends from EVERY commit of the public mirror. So a test that
    reads one of them by a fixed path passes on every developer machine and
    fails only on the public repo's CI - the one place the filtered tree is
    what actually runs. There is no local signal at all.

    Found 2026-09-02: both CLAUDE.md budget gates did exactly that and turned
    public main red the moment v0.8.7.3 was pushed - a release-time failure,
    after the tag was cut and the Release published. Same shape as the
    scrub-map-fixture trap already recorded in the release skill: the working
    repo and the published repo are different trees, and only one of them runs
    in CI.

    Guard the read with this fixture. Locally the file is there and the gate
    runs; on the filtered tree it is absent and the gate skips, which is
    correct - a rule about CLAUDE.md has nothing to say about a mirror that
    deliberately has no CLAUDE.md.
    """
    def _resolve(relpath: str) -> Path:
        path = ROOT / relpath
        if not path.exists():
            pytest.skip(
                f"{relpath} is stripped from the published mirror by "
                f"tools/publish_mirror.py - this gate applies to the working "
                f"repo only")
        return path
    return _resolve


# ── Qt objects must not outlive the QApplication ──────────────────────────────

@pytest.fixture
def destroy_qt():
    """Destroy the Qt objects a test made, NOW, and nobody else's.

    **The trap, both halves of it.** A ``QWidget`` a test leaves alive is
    destroyed at interpreter shutdown, by which point the ``QApplication`` may
    already be gone - and destroying a widget without an application aborts
    the process. The run reaches ``[100%]`` with every test passing and then
    dies with an access violation and no summary, so there is no failing test
    to look at and the exit code is the only evidence.

    ``deleteLater`` does not fix it: it only *queues* the delete, and if
    nothing dispatches that queue before exit the object is in exactly the
    same place. Dispatching it with
    ``QCoreApplication.sendPostedEvents(None, DeferredDelete)`` is worse,
    because ``None`` means EVERY object: it runs deletes other suites queued
    and have not finished with, which is what crashed the full run at ~96% on
    2026-10-05 (the fix then removed the flush from the card-game fixtures and
    left three more in tests/ui).

    So: destroy this object and only this object, while the application is
    certainly still alive. ``shiboken6.delete`` runs the C++ destructor on the
    spot - no queue, no other objects, nothing deferred.

    Use this instead of ``deleteLater()`` in any test or fixture teardown.
    """
    import shiboken6

    def _destroy(*objects) -> None:
        for obj in objects:
            if obj is None or not shiboken6.isValid(obj):
                continue
            close = getattr(obj, "close", None)
            if close is not None:
                close()
            shiboken6.delete(obj)

    return _destroy


@pytest.fixture(scope="session", autouse=True)
def _nothing_qt_outlives_the_application():
    """The safety net under ``destroy_qt``: at the END of the session, take
    down every window still standing while the application is still there.

    Destroying a window destroys its children with it, and a ``QObject``'s
    destructor drops any event still queued for it - so taking the windows
    down also clears every ``deleteLater`` left pending underneath them. That
    is why this does NOT end with an app-wide
    ``sendPostedEvents(None, DeferredDelete)``: such a flush would buy nothing
    here and carries the very risk that crashed the run on 2026-10-05.

    It is a net, not permission to leak: a test that shows a window still
    closes it, because a window left standing is also a window the NEXT test
    can grab pixels from by accident.
    """
    yield
    try:
        from PySide6.QtWidgets import QApplication
        import shiboken6
    except Exception:            # a run with no Qt installed owes nothing here
        return
    if QApplication.instance() is None:   # no Qt test ran; nothing was created
        return
    for widget in list(QApplication.topLevelWidgets()):
        if not shiboken6.isValid(widget):
            continue
        widget.close()
        shiboken6.delete(widget)


def wear_theme(monkeypatch, worn="halloween", stored=None):
    """Dress the app in a theme, for the Puppet Master gate.

    ``constants.puppet_master_enabled`` reads the WORN theme off the default
    SettingsManager (2026-11-03: he follows the halloween THEME, not the
    calendar), so a test that flips ``PUPPET_MASTER_ENABLED`` on also has to
    dress the app or he stays asleep.

    The gate imports SettingsManager LAZILY, so patching the attribute on the
    settings module reaches it while a test file's own module-level
    ``SettingsManager`` name still points at the real class - a test can go on
    building a real one in ``tmp_path`` for everything else.

    ``stored`` is the theme the user PICKED, which only differs from ``worn``
    in season; pass ``stored="professional"`` for the user who is shown the
    halloween look but keeps the sober feature set.
    """
    class _Settings:
        def get_theme(self):
            return worn

        def is_professional(self):
            return (worn if stored is None else stored) == "professional"

    monkeypatch.setattr("techdeck.core.settings.SettingsManager",
                        lambda *a, **k: _Settings())
