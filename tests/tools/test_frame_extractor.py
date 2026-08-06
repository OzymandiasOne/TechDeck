"""Tests for the DevKit Frame Extractor panel."""

import sys

from tools.devkit.diagnostics import ROOT
from tools.devkit.frame_extractor import FrameExtractorPanel

SCRIPT = str(ROOT / "tools" / "extract_frames.py")


def test_command_defaults(qapp, tmp_path):
    video = tmp_path / "clip.mp4"
    video.touch()
    panel = FrameExtractorPanel()
    panel.video.setText(str(video))
    assert panel._command() == [
        sys.executable, SCRIPT, str(video), "--fps", "1"]


def test_command_with_window_and_rate(qapp, tmp_path):
    video = tmp_path / "clip.mp4"
    video.touch()
    panel = FrameExtractorPanel()
    panel.video.setText(str(video))
    panel.fps.setValue(2.5)
    panel.start.setText("0:05")
    panel.end.setText("1:30")
    assert panel._command() == [
        sys.executable, SCRIPT, str(video), "--fps", "2.5",
        "--start", "0:05", "--end", "1:30"]


def test_start_refuses_without_video(qapp):
    panel = FrameExtractorPanel()
    panel._start()
    assert panel._process is None
    assert panel.status.text() == "CHOOSE A VIDEO FILE FIRST"
    assert panel.run_btn.isEnabled()


def test_start_refuses_missing_file(qapp, tmp_path):
    panel = FrameExtractorPanel()
    panel.video.setText(str(tmp_path / "nope.mp4"))
    panel._start()
    assert panel._process is None
    assert panel.status.text() == "CHOOSE A VIDEO FILE FIRST"


def test_verdict_phrasing(qapp):
    panel = FrameExtractorPanel()
    assert panel._verdict(0)[1] == "success"
    assert panel._verdict(1) == (
        "NO FRAMES EXPORTED (window past end? see log)", "error")
    assert panel._verdict(2)[1] == "error"


def test_registry_contains_frame_extractor():
    from tools.devkit.registry import DEV_TOOLS
    assert any(t.key == "frame_extractor" for t in DEV_TOOLS)
