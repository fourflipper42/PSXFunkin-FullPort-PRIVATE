#!/usr/bin/env python3
"""Convert an FNF video cutscene to a PS2-friendly paged indexed stream.

Frames are scaled/padded to 320x180 at 15 fps by default, grouped 3x5 into
960x900 T8 texture pages, and synchronized to 48 kHz stereo s16 PCM audio.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

MAGIC = b"FCUT"
VERSION = 1
HEADER = struct.Struct("<4sHHHHHHIHHHH")


def load_texture_converter():
    path = Path(__file__).with_name("convert_texture.py")
    spec = importlib.util.spec_from_file_location("convert_texture_cutscene", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def extract_frames(video: Path, frame_dir: Path, width: int, height: int, fps: int) -> list[Path]:
    frame_dir.mkdir(parents=True, exist_ok=True)
    vf = (
        f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
    )
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-vf", vf, "-vsync", "0",
        str(frame_dir / "%06d.png"),
    ])
    frames = sorted(frame_dir.glob("*.png"))
    if not frames:
        raise RuntimeError(f"ffmpeg produced no frames for {video}")
    return frames


def extract_audio(video: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-vn", "-ar", "48000", "-ac", "2",
        "-f", "s16le", str(output),
    ])
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg produced no cutscene audio for {video}")


def build_pages(
    frames: list[Path],
    output: Path,
    width: int,
    height: int,
    columns: int,
    rows: int,
) -> int:
    texture = load_texture_converter()
    frames_per_page = columns * rows
    page_count = math.ceil(len(frames) / frames_per_page)
    page_width = columns * width
    page_height = rows * height

    for page_index in range(page_count):
        page = Image.new("RGBA", (page_width, page_height), (0, 0, 0, 255))
        start = page_index * frames_per_page
        end = min(start + frames_per_page, len(frames))
        for frame_index in range(start, end):
            local = frame_index - start
            x = (local % columns) * width
            y = (local // columns) * height
            with Image.open(frames[frame_index]) as image:
                page.alpha_composite(image.convert("RGBA"), (x, y))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            temp_png = Path(tmp.name)
        try:
            page.save(temp_png, optimize=False)
            texture.convert(temp_png, output / f"P{page_index:03d}.FPTX")
        finally:
            temp_png.unlink(missing_ok=True)
    return page_count


def convert(
    video: Path,
    output: Path,
    width: int = 320,
    height: int = 180,
    fps: int = 15,
    columns: int = 3,
    rows: int = 5,
) -> dict:
    video = video.resolve()
    output = output.resolve()
    if not video.is_file():
        raise FileNotFoundError(video)
    if width <= 0 or height <= 0 or fps <= 0 or columns <= 0 or rows <= 0:
        raise ValueError("cutscene dimensions/fps/page grid must be positive")
    if columns * width > 1024 or rows * height > 1024:
        raise ValueError("cutscene page exceeds 1024x1024 PS2 streaming target")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="fnf-ps2-cutscene-") as temp_name:
        frame_dir = Path(temp_name) / "frames"
        frames = extract_frames(video, frame_dir, width, height, fps)
        extract_audio(video, output / "AUDIO.PCM")
        page_count = build_pages(frames, output, width, height, columns, rows)

    header = HEADER.pack(
        MAGIC,
        VERSION,
        0,
        width,
        height,
        fps,
        1,
        len(frames),
        columns,
        rows,
        page_count,
        0,
    )
    (output / "CUT.FCUT").write_bytes(header)
    result = {
        "source": video.as_posix(),
        "width": width,
        "height": height,
        "fps": fps,
        "frames": len(frames),
        "columns": columns,
        "rows": rows,
        "pages": page_count,
        "audioBytes": (output / "AUDIO.PCM").stat().st_size,
    }
    print(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=180)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--rows", type=int, default=5)
    args = parser.parse_args()
    convert(
        args.video,
        args.output,
        args.width,
        args.height,
        args.fps,
        args.columns,
        args.rows,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
