"""Tests for the DevKit diagnostics panels (subprocess runners)."""

import sys

from tools.devkit.diagnostics import (
    ROOT, _DiagnosticsPanel, AutomatedTestsPanel, ShipReadinessPanel,
    PixelLintPanel,
)


class _EchoPanel(_DiagnosticsPanel):
    """Minimal concrete panel running a fixed python one-liner."""

    def __init__(self, code: str, parent=None):
        self._code = code
        super().__init__(parent)

    def _build_controls(self, row):
        pass

    def _command(self):
        return [sys.executable, "-c", self._code]


def _run_to_completion(qapp, panel, timeout_ms=30000):
    panel._start()
    assert panel._process is not None
    finished = panel._process.waitForFinished(timeout_ms)
    assert finished, "diagnostics subprocess did not finish in time"
    qapp.processEvents()  # deliver queued finished/teardown signals


def test_runner_streams_output_and_reports_pass(qapp):
    panel = _EchoPanel("print('diag-hello')")
    _run_to_completion(qapp, panel)
    assert "diag-hello" in panel.output.toPlainText()
    assert panel.status.text() == "PASSED"
    assert panel._process is None
    assert panel.run_btn.isEnabled()
    assert not panel.stop_btn.isEnabled()


def test_runner_reports_failure_exit_code(qapp):
    panel = _EchoPanel("import sys; sys.exit(3)")
    _run_to_completion(qapp, panel)
    assert panel.status.text() == "FAILED (exit 3)"
    assert panel.run_btn.isEnabled()


def test_runner_sets_utf8_env_and_repo_cwd(qapp):
    panel = _EchoPanel(
        "import os; print(os.environ['PYTHONUTF8'], os.getcwd())")
    _run_to_completion(qapp, panel)
    out = panel.output.toPlainText()
    assert "1 " in out
    assert str(ROOT) in out


def test_test_runner_command_scoping(qapp):
    panel = AutomatedTestsPanel()
    assert panel._command() == [sys.executable, "-m", "pytest"]
    # This test file itself must be discoverable as a scope option.
    rel = "tests/tools/test_diagnostics.py"
    idx = panel.scope.findData(rel)
    assert idx > 0
    panel.scope.setCurrentIndex(idx)
    panel.keyword.setText("streams")
    panel.verbose.setChecked(True)
    assert panel._command() == [
        sys.executable, "-m", "pytest", rel, "-k", "streams", "-v"]


def test_ship_readiness_command(qapp):
    panel = ShipReadinessPanel()
    script = str(ROOT / "tools" / "check_ship_readiness.py")
    assert panel._command() == [sys.executable, script]
    panel.load_plugins.setChecked(True)
    assert panel._command() == [sys.executable, script, "--load"]


def test_pixel_lint_command(qapp):
    panel = PixelLintPanel()
    script = str(ROOT / "tools" / "check_pixel_style.py")
    assert panel._command() == [sys.executable, script, "assets/sprites"]
    panel.targets.setText("assets/mrbeans.tdart key:qr_code")
    panel.profile.setCurrentText("logo")
    assert panel._command() == [
        sys.executable, script, "assets/mrbeans.tdart", "key:qr_code",
        "--profile", "logo"]


def test_registry_contains_diagnostics_tools():
    from tools.devkit.registry import DEV_TOOLS
    keys = [t.key for t in DEV_TOOLS]
    for expected in ("automated_tests", "ship_readiness", "pixel_lint"):
        assert expected in keys
