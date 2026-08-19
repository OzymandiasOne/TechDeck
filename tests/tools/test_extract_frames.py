"""Tests for tools/extract_frames.py — the video-to-stills exporter.

SKIPPED where OpenCV is absent. `extract_frames` is a DevKit-only utility (it
turns a screen recording into stills for review) and nothing in the shipped app
imports it, so `opencv-python` is deliberately NOT in requirements-dev.txt — a
~40MB dependency for a tool no user ever runs.

That has to be a SKIP rather than a bare import, though: an unconditional
`import cv2` at module scope fails at COLLECTION, and a collection error aborts
the whole pytest run ("Interrupted: 1 error during collection"). It doesn't
cost you one test, it costs you all of them. Caught on the public repo's CI
during the v0.8.6.13 release push — the runner has no OpenCV, so zero tests ran
while the local suite was fully green.
"""

import argparse

import numpy as np
import pytest

cv2 = pytest.importorskip(
    "cv2", reason="opencv-python is a DevKit-only dependency, not installed in CI")

from tools.extract_frames import extract_frames, parse_timestamp  # noqa: E402


@pytest.fixture(scope="module")
def sample_video(tmp_path_factory):
    """A 5-second 10fps MJPG clip whose frame color encodes its index."""
    path = tmp_path_factory.mktemp("video") / "sample.avi"
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter.fourcc(*"MJPG"), 10.0, (64, 48))
    assert writer.isOpened()
    for i in range(50):
        frame = np.full((48, 64, 3), (i * 5) % 256, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return path


def test_parse_timestamp_forms():
    assert parse_timestamp("90") == 90.0
    assert parse_timestamp("12.5") == 12.5
    assert parse_timestamp("1:30") == 90.0
    assert parse_timestamp("0:01:30.25") == 90.25


def test_parse_timestamp_rejects_junk():
    for bad in ("abc", "1:2:3:4", "-5"):
        with pytest.raises(argparse.ArgumentTypeError):
            parse_timestamp(bad)


def test_full_video_at_1fps(sample_video, tmp_path):
    written = extract_frames(sample_video, tmp_path / "out", fps=1.0)
    # 5s @ 1fps -> captures at t=0,1,2,3,4 (5s is past the last frame)
    assert len(written) == 5
    assert written[0].name == "frame_0000_t0.00s.png"
    assert all(p.is_file() for p in written)


def test_window_and_rate(sample_video, tmp_path):
    written = extract_frames(
        sample_video, tmp_path / "out", fps=2.0, start=1.0, end=3.0)
    # t=1.0, 1.5, 2.0, 2.5, 3.0
    assert len(written) == 5
    assert written[0].name.endswith("t1.00s.png")
    assert written[-1].name.endswith("t3.00s.png")


def test_frames_come_from_the_right_moment(sample_video, tmp_path):
    written = extract_frames(
        sample_video, tmp_path / "out", fps=1.0, start=2.0, end=2.0)
    img = cv2.imread(str(written[0]))
    assert img is not None
    # frame 20 (t=2.0) was painted value (20*5)%256 = 100; MJPG is lossy, allow slack
    assert abs(int(img[0, 0, 0]) - 100) <= 6


def test_max_width_downscales(sample_video, tmp_path):
    written = extract_frames(
        sample_video, tmp_path / "out", fps=1.0, end=0.0, max_width=32)
    img = cv2.imread(str(written[0]))
    assert img is not None
    assert img.shape[1] == 32
    assert img.shape[0] == 24  # aspect preserved


def test_empty_window_past_end(sample_video, tmp_path):
    written = extract_frames(
        sample_video, tmp_path / "out", fps=1.0, start=99.0)
    assert written == []
