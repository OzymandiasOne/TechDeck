"""Export frames from a video file as images for visual review.

Claude (and humans skimming a PR) cannot watch a video; this breaks one into
timestamped stills. Frames are sampled at --fps (export rate, independent of the
video's native rate) across an optional --start/--end window (default: the full
video).

Usage:
    python tools/extract_frames.py VIDEO [--fps N] [--start TS] [--end TS]
                                         [--out DIR] [--max-width PX] [--format EXT]

Timestamps accept plain seconds ("90", "12.5") or clock form ("1:30", "0:01:30.25").
Output files are named frame_NNNN_t<seconds>s.<ext> so a filename alone pins the
moment in the video.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2


def parse_timestamp(value: str) -> float:
    """'90' / '12.5' / '1:30' / '0:01:30.25' -> seconds."""
    parts = value.strip().split(":")
    if len(parts) > 3:
        raise argparse.ArgumentTypeError(f"bad timestamp: {value!r}")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise argparse.ArgumentTypeError(f"bad timestamp: {value!r}") from None
    seconds = 0.0
    for n in nums:
        seconds = seconds * 60 + n
    if seconds < 0:
        raise argparse.ArgumentTypeError(f"negative timestamp: {value!r}")
    return seconds


def extract_frames(
    video: Path,
    out_dir: Path,
    fps: float,
    start: float = 0.0,
    end: float | None = None,
    max_width: int = 1600,
    image_format: str = "png",
) -> list[Path]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"Could not open video: {video}")

    native_fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration = frame_count / native_fps if native_fps > 0 else 0.0

    print(f"{video.name}: {width}x{height}, {native_fps:.3f} fps native, "
          f"{duration:.2f}s ({frame_count} frames)")
    if end is not None and start > end:
        cap.release()
        raise SystemExit(f"--start ({start:.2f}s) is after --end ({end:.2f}s)")
    if end is None or (duration and end > duration):
        end = duration if duration else end

    out_dir.mkdir(parents=True, exist_ok=True)
    interval = 1.0 / fps
    next_capture = start
    written: list[Path] = []
    frame_idx = -1

    # Sequential grab()/retrieve() walk: grab() skips decoding unwanted frames,
    # and unlike CAP_PROP_POS_MSEC seeking it is exact on every codec.
    while True:
        if not cap.grab():
            break
        frame_idx += 1
        t = frame_idx / native_fps if native_fps > 0 else float(frame_idx)
        if t < next_capture - (0.5 / native_fps if native_fps > 0 else 0.0):
            continue
        if end is not None and t > end + 1e-9:
            break
        ok, frame = cap.retrieve()
        if not ok:
            continue
        if max_width and frame.shape[1] > max_width:
            scale = max_width / frame.shape[1]
            frame = cv2.resize(
                frame, (max_width, round(frame.shape[0] * scale)),
                interpolation=cv2.INTER_AREA,
            )
        name = f"frame_{len(written):04d}_t{t:.2f}s.{image_format}"
        dest = out_dir / name
        if not cv2.imwrite(str(dest), frame):
            cap.release()
            raise SystemExit(f"Failed to write {dest}")
        written.append(dest)
        next_capture += interval

    cap.release()
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export frames from a video file as images for visual review.")
    parser.add_argument("video", type=Path, help="video file to sample")
    parser.add_argument("--fps", type=float, default=1.0,
                        help="frames to export per second of video (default: 1)")
    parser.add_argument("--start", type=parse_timestamp, default=0.0,
                        help="start timestamp (seconds or [HH:]MM:SS; default: 0)")
    parser.add_argument("--end", type=parse_timestamp, default=None,
                        help="end timestamp (default: end of video)")
    parser.add_argument("--out", type=Path, default=None,
                        help="output folder (default: <video stem>_frames beside the video)")
    parser.add_argument("--max-width", type=int, default=1600,
                        help="downscale frames wider than this; 0 keeps original size "
                             "(default: 1600)")
    parser.add_argument("--format", dest="image_format", choices=("png", "jpg"),
                        default="png", help="image format (default: png)")
    args = parser.parse_args(argv)

    if args.fps <= 0:
        parser.error("--fps must be positive")
    if not args.video.is_file():
        parser.error(f"video not found: {args.video}")
    out_dir = args.out or args.video.parent / f"{args.video.stem}_frames"

    written = extract_frames(
        args.video, out_dir, args.fps,
        start=args.start, end=args.end,
        max_width=args.max_width, image_format=args.image_format,
    )
    if not written:
        print("No frames exported (window past end of video?)")
        return 1
    print(f"Exported {len(written)} frames -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
