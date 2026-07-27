"""DevKit diagnostics panels — run the repo's checkers from inside TechDeck.

One shared subprocess-runner base (`_DiagnosticsPanel`) and three concrete
panels registered in the DevKit picker:

- Automated Tests   → python -m pytest         (scope to a file, -k filter)
- Ship Readiness    → tools/check_ship_readiness.py  (optional --load)
- Pixel Style Lint  → tools/check_pixel_style.py     (targets + profile)

Everything runs as a SUBPROCESS, never in-process: TechDeck already owns the
one-and-only QApplication, and the test conftest boots its own offscreen one —
they cannot share a process. A subprocess also means a hung or crashing check
can't take the app down, and Cancel is just killing it. Source-only — this
package is excluded from the frozen build, and in dev mode sys.executable is
the real Python so all three commands exist.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QPlainTextEdit, QLineEdit, QCheckBox,
)
from PySide6.QtCore import QProcess, QProcessEnvironment
from PySide6.QtGui import QFont

from techdeck.ui.theme_aware import ThemeAware

ROOT = Path(__file__).resolve().parents[2]


class _DiagnosticsPanel(QWidget, ThemeAware):
    """Shared runner: a controls row + Run/Stop, streaming a subprocess's
    merged output into a monospace log with a pass/fail status line. Verdict
    colors are palette ROLES ('success'/'error') resolved at paint time, so a
    live theme switch restyles the log and the last verdict correctly."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = None
        self._status_role = None   # None | 'success' | 'error'

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self._build_controls(controls)
        controls.addStretch()
        self.run_btn = QPushButton("Run")
        self.run_btn.setMinimumHeight(30)
        self.run_btn.setMinimumWidth(80)
        self.run_btn.clicked.connect(self._start)
        controls.addWidget(self.run_btn)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setMinimumHeight(30)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        controls.addWidget(self.stop_btn)
        outer.addLayout(controls)

        self.status = QLabel("Ready.")
        outer.addWidget(self.status)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(9)
        self.output.setFont(mono)
        outer.addWidget(self.output, 1)

        self.setup_theme_awareness()

    def apply_theme(self):
        pal = self.get_current_palette()
        # Console treatment for the log — otherwise it renders invisibly flush
        # with the panel surface.
        self.output.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {pal.console_bg}; "
            f"color: {pal.console_text}; border: 1px solid {pal.border}; "
            f"border-radius: 6px; }}")
        self._restyle_status()

    # ── subclass contract ────────────────────────────────────────────────

    def _build_controls(self, row: QHBoxLayout):
        """Add this panel's scoping widgets to the controls row."""
        raise NotImplementedError

    def _command(self) -> list:
        """The subprocess argv (first element is the program)."""
        raise NotImplementedError

    # ── run machinery ────────────────────────────────────────────────────

    def _start(self):
        if self._process is not None:
            return
        cmd = self._command()
        self.output.clear()
        self.output.appendPlainText("$ " + " ".join(cmd) + "\n")
        self._set_status("Running…", None)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        proc = QProcess(self)
        proc.setWorkingDirectory(str(ROOT))
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUTF8", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        proc.setProcessEnvironment(env)
        proc.readyReadStandardOutput.connect(self._on_output)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        self._process = proc
        proc.start(cmd[0], cmd[1:])

    def _stop(self):
        if self._process is not None:
            self._process.kill()

    def _on_output(self):
        if self._process is None:
            return
        text = bytes(self._process.readAllStandardOutput().data()).decode(
            "utf-8", errors="replace")
        if text:
            self.output.moveCursor(self.output.textCursor().MoveOperation.End)
            self.output.insertPlainText(text)
            self.output.moveCursor(self.output.textCursor().MoveOperation.End)

    def _on_finished(self, exit_code, exit_status):
        self._on_output()  # flush any buffered tail
        if exit_status == QProcess.ExitStatus.CrashExit:
            self._set_status("STOPPED", "error")
        else:
            self._set_status(*self._verdict(exit_code))
        self._teardown()

    def _verdict(self, exit_code) -> tuple:
        """(status text, palette role) for a normal exit — override to phrase
        what a nonzero exit means for this check."""
        if exit_code == 0:
            return "PASSED", "success"
        return f"FAILED (exit {exit_code})", "error"

    def _on_error(self, error):
        # finished() does not fire for FailedToStart — clean up here.
        if error == QProcess.ProcessError.FailedToStart:
            self._set_status("FAILED TO START", "error")
            self._teardown()

    def _teardown(self):
        if self._process is not None:
            self._process.deleteLater()
            self._process = None
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _set_status(self, text, role):
        self._status_role = role
        self.status.setText(text)
        self._restyle_status()

    def _restyle_status(self):
        pal = self.get_current_palette()
        color = {"success": pal.success, "error": pal.error}.get(self._status_role)
        self.status.setStyleSheet(
            f"font-weight: 600; color: {color};" if color else "font-weight: 600;")


class AutomatedTestsPanel(_DiagnosticsPanel):
    """python -m pytest, scoped to all tests or one file, with a -k filter."""

    def _build_controls(self, row: QHBoxLayout):
        row.addWidget(QLabel("Scope"))
        self.scope = QComboBox()
        self.scope.setMinimumWidth(260)
        self.scope.addItem("All tests", None)
        tests_dir = ROOT / "tests"
        for f in sorted(tests_dir.rglob("test_*.py")):
            rel = f.relative_to(ROOT).as_posix()
            self.scope.addItem(rel, rel)
        row.addWidget(self.scope)
        self.keyword = QLineEdit()
        self.keyword.setPlaceholderText("keyword filter (-k), optional")
        self.keyword.setMinimumWidth(180)
        row.addWidget(self.keyword)
        self.verbose = QCheckBox("Verbose")
        row.addWidget(self.verbose)

    def _command(self) -> list:
        cmd = [sys.executable, "-m", "pytest"]
        scoped = self.scope.currentData()
        if scoped:
            cmd.append(scoped)
        kw = self.keyword.text().strip()
        if kw:
            cmd += ["-k", kw]
        if self.verbose.isChecked():
            cmd.append("-v")
        return cmd


class ShipReadinessPanel(_DiagnosticsPanel):
    """tools/check_ship_readiness.py — the gate build.ps1 enforces."""

    def _build_controls(self, row: QHBoxLayout):
        self.load_plugins = QCheckBox("Also load every plugin (--load)")
        row.addWidget(self.load_plugins)

    def _command(self) -> list:
        cmd = [sys.executable, str(ROOT / "tools" / "check_ship_readiness.py")]
        if self.load_plugins.isChecked():
            cmd.append("--load")
        return cmd


class PixelLintPanel(_DiagnosticsPanel):
    """tools/check_pixel_style.py over PNG/.tdart targets."""

    def _build_controls(self, row: QHBoxLayout):
        row.addWidget(QLabel("Targets"))
        self.targets = QLineEdit("assets/sprites")
        self.targets.setToolTip(
            "Space-separated: a dir, a .png/.tdart file, or key:NAME")
        self.targets.setMinimumWidth(240)
        row.addWidget(self.targets)
        row.addWidget(QLabel("Profile"))
        self.profile = QComboBox()
        # (auto) omits --profile: the linter picks logo for .png, sprite
        # for .tdart.
        self.profile.addItems(["(auto)", "logo", "sprite", "character"])
        row.addWidget(self.profile)

    def _command(self) -> list:
        cmd = [sys.executable, str(ROOT / "tools" / "check_pixel_style.py")]
        cmd += self.targets.text().split()
        if self.profile.currentIndex() > 0:
            cmd += ["--profile", self.profile.currentText()]
        return cmd

    def _verdict(self, exit_code):
        # Exit 1 means the ART failed the style spec, not that the linter
        # broke — phrase it so a FAIL verdict isn't read as a tool error.
        if exit_code == 0:
            return "PASS (any warnings are in the log)", "success"
        return "STYLE FINDINGS — the art fails the style spec (see log)", "error"
