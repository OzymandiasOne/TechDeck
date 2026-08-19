"""UpdateDialog failure UX: a failed download must leave a way to retry.

Before this, _update_error_ui disabled the Update button — a dropped
connection on the 300+ MB download meant reopening the dialog to try again,
and on a MANDATORY update the only live button left was "Quit TechDeck".
"""

from techdeck.core.update_checker import UpdateInfo
from techdeck.ui.dialogs.update_dialog import UpdateDialog


def _info():
    return UpdateInfo({
        "version": "9.9.9",
        "download_url": "https://example.invalid/TechDeck-Setup.exe",
        "release_notes": "Test notes.",
    })


def test_failed_download_reenables_update_as_try_again(qapp):
    dialog = UpdateDialog(_info(), mandatory=False)
    try:
        dialog._update_error_ui("Network error: connection dropped")

        assert dialog.update_btn.isEnabled(), (
            "a failed download must leave the user able to retry")
        assert dialog.update_btn.text() == "Try Again"
        assert dialog.later_btn.isEnabled()
        assert not dialog.progress_bar.isVisible()
        assert "connection dropped" in dialog.status_label.text()
    finally:
        dialog.deleteLater()


def test_quit_button_stamps_a_clean_exit(qapp, monkeypatch):
    """The mandatory dialog's Quit bypasses closeEvent — without the stamp
    it read as a crash and would trigger the crash-report offer on the
    next start."""
    import pytest as _pytest
    from techdeck.core import hang_watchdog

    marked = []
    monkeypatch.setattr(hang_watchdog, "mark_clean_exit",
                        lambda: marked.append(True))

    dialog = UpdateDialog(_info(), mandatory=True)
    try:
        with _pytest.raises(SystemExit):
            dialog._quit_app()
        assert marked == [True]
    finally:
        dialog.deleteLater()


def test_mandatory_failed_download_is_not_quit_only(qapp):
    """The worst case: a mandatory update whose download failed used to
    leave 'Quit TechDeck' as the ONLY enabled button."""
    dialog = UpdateDialog(_info(), mandatory=True)
    try:
        dialog._update_error_ui("Download failed: HTTP 503")

        assert dialog.update_btn.isEnabled()
        assert dialog.update_btn.text() == "Try Again"
        assert dialog.quit_btn.isEnabled()
    finally:
        dialog.deleteLater()
