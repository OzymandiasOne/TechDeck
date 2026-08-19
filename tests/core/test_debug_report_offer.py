"""The crash-report offer contract, and the exits that must not look like
crashes.

The debug report is the whole remote-support story, but it sat behind
Settings -> Help & Feedback where nobody found it unaided. The shell now
offers it on the start AFTER a dirty exit — which only works if deliberate
non-closeEvent exits (auto-update install, the mandatory dialog's Quit)
stamp themselves clean first, or every update would trigger the offer.
"""

import pytest

from techdeck.core import hang_watchdog
from techdeck.core import update_downloader as ud
from techdeck.core.debug_report import should_offer_debug_report


# ------------------------------------------------------------ the decision

def test_dirty_exit_offers():
    assert should_offer_debug_report({"clean_exit": False}) is True


def test_clean_exit_does_not_offer():
    assert should_offer_debug_report({"clean_exit": True}) is False


def test_no_previous_session_does_not_offer():
    assert should_offer_debug_report(None) is False


def test_old_format_snapshot_without_the_key_does_not_offer():
    # Only an EXPLICIT false counts — a pre-watchdog snapshot must not nag.
    assert should_offer_debug_report({"at": "2026-08-17 09:00:00"}) is False


def test_garbage_input_does_not_offer():
    assert should_offer_debug_report("not a dict") is False
    assert should_offer_debug_report([]) is False


# ------------------------------------------------ exits that stamp clean

def test_run_installer_and_exit_marks_clean_exit(monkeypatch, tmp_path):
    """The auto-update restart bypasses closeEvent (sys.exit from a timer
    slot) — before this stamp, every successful update recorded
    clean_exit:false and read as a crash in the next debug report."""
    marked = []
    monkeypatch.setattr(hang_watchdog, "mark_clean_exit",
                        lambda: marked.append(True))
    monkeypatch.setattr(ud.subprocess, "Popen", lambda *a, **k: None)

    installer = tmp_path / "TechDeck-Setup-9.9.9.exe"
    installer.write_bytes(b"fake installer")

    # Non-frozen path: launches the installer and exits without the .bat.
    with pytest.raises(SystemExit):
        ud.run_installer_and_exit(str(installer))
    assert marked == [True]
