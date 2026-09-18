"""ReportDialog - the pop-up a plugin's finished report is read in.

Two things here are easy to get wrong and invisible until somebody squints at a
screenshot:

  * the body MUST render fixed-pitch. The report is column-aligned plain text
    with ruled dividers, and the app-level stylesheet sets font-family on
    QWidget - QSS beats setFont(), so a setFont(FixedFont) renders proportional
    and every column and divider comes out ragged. The font therefore has to be
    in the widget's OWN stylesheet, and it must not wrap.
  * Save writes to the path the caller chose (the folder the run was pointed at),
    and a failure has to show in the dialog instead of raising into the GUI loop.
"""

from techdeck.ui.dialogs.report_dialog import ReportDialog

BODY = "911 INSPECTION SHEET FILL-IN\n" + "=" * 40 + "\n  67-201   H4524567-201\n"


def _dialog(qapp, save_path=""):
    dlg = ReportDialog("A Report", "what it is", BODY, save_path)
    dlg.show()
    qapp.processEvents()
    return dlg


def _body_widget(dlg):
    """The report view. NOTE: callers must keep `dlg` alive for the assertion -
    Qt deletes a dialog whose last Python reference drops, even mid-expression,
    which is the very trap this dialog's docstring warns about (Hard Rule 4)."""
    from PySide6.QtWidgets import QPlainTextEdit

    view = dlg.findChild(QPlainTextEdit)
    assert view is not None, "the dialog has no report view"
    return view


# ------------------------------------------------------------------ rendering

def test_body_is_shown_verbatim(qapp):
    dlg = _dialog(qapp)
    assert _body_widget(dlg).toPlainText() == BODY


def test_body_font_is_fixed_pitch_via_its_own_stylesheet(qapp):
    """The regression: setFont() loses to the app-level QSS font-family."""
    dlg = _dialog(qapp)
    css = _body_widget(dlg).styleSheet()
    assert "font-family:" in css
    assert "monospace" in css


def test_body_does_not_wrap(qapp):
    """Wrapping would shuffle the number columns out of line."""
    from PySide6.QtWidgets import QPlainTextEdit
    dlg = _dialog(qapp)
    view = _body_widget(dlg)
    assert view.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap


def test_body_is_read_only(qapp):
    dlg = _dialog(qapp)
    assert _body_widget(dlg).isReadOnly()


def test_dialog_is_modeless(qapp):
    """The run is over by the time this opens - it must not block the app."""
    dlg = _dialog(qapp)
    assert dlg.isModal() is False


# ---------------------------------------------------------------------- save

def test_save_writes_the_body_to_the_given_path(qapp, tmp_path):
    target = tmp_path / "911 Inspection Sheet Fill-In - 503891 - 2026-09-01.txt"
    dlg = _dialog(qapp, str(target))
    dlg._save()
    qapp.processEvents()
    assert target.read_text(encoding="utf-8") == BODY
    assert dlg.saved_to == str(target)


def test_nothing_is_written_until_the_button_is_pressed(qapp, tmp_path):
    """Saving is the user's choice - opening the report must not drop a file."""
    target = tmp_path / "report.txt"
    dlg = _dialog(qapp, str(target))
    assert not target.exists()
    assert dlg.saved_to == ""


def test_a_failed_save_is_reported_in_the_dialog_not_raised(qapp, tmp_path):
    """A GUI-thread exception would take the window down with it."""
    target = tmp_path / "no-such-dir" / "report.txt"
    dlg = _dialog(qapp, str(target))
    dlg._save()                      # must not raise
    assert dlg.saved_to == ""
    assert "could not save" in dlg._status.text().lower()


def test_with_no_save_path_there_is_no_save_button(qapp):
    from PySide6.QtWidgets import QPushButton
    dlg = _dialog(qapp)
    labels = [b.text() for b in dlg.findChildren(QPushButton)]
    assert labels == ["Close"]


def test_the_status_line_names_the_folder_it_will_save_into(qapp, tmp_path):
    """So the reader knows where the copy lands before they press it."""
    target = tmp_path / "sub" / "report.txt"
    dlg = _dialog(qapp, str(target))
    assert str(tmp_path / "sub") in dlg._status.text()
