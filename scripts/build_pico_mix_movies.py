#!/usr/bin/env python3
"""Convert the official Stress Pico Mix opening and ending cutscenes to PS1 STR."""
# CI trigger for the Pico asset exception-annotation probe.
from __future__ import annotations

import argparse
import json
import math
import struct
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "ps1asset"))
from animateatlas_flatten import AnimateAtlas, render_leaves

SECTOR = 2336
STR_MAGIC = b"\x60\x01\x01\x80"
FPS = 15


def encoded_frame_count(path: Path) -> int:
    data = path.read_bytes()
    if len(data) % SECTOR:
        raise RuntimeError(f"{path} is not 2336-byte sector aligned")
    maximum = 0
    for offset in range(0, len(data), SECTOR):
        sector = data[offset:offset + SECTOR]
        if sector[2] == 0x48 and sector[8:12] == STR_MAGIC:
            maximum = max(maximum, struct.unpack_from("<I", sector, 16)[0])
    if maximum <= 0:
        raise RuntimeError(f"no STR frames found in {path}")
    return maximum


def build_ending(atlas_path: Path, audio: Path, ffmpeg: Path, temporary: Path) -> Path:
    atlas = AnimateAtlas(atlas_path)
    atlas_frames = atlas.timeline_length(atlas.root["TL"])
    frame_count = math.ceil((320 / 24) * FPS)
    silent = temporary / "stress-pico-ending-silent.mp4"
    process = subprocess.Popen([
        str(ffmpeg), "-y", "-loglevel", "error", "-f", "rawvideo",
        "-pix_fmt", "rgb24", "-s", "320x240", "-r", str(FPS), "-i", "-",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12",
        "-pix_fmt", "yuv420p", str(silent),
    ], stdin=subprocess.PIPE)
    assert process.stdin is not None
    for output_frame in range(frame_count):
        source_frame = min(atlas_frames - 1, math.floor(output_frame * 24 / FPS))
        sprite, _ = render_leaves(atlas.leaves_for_frame(source_frame))
        sprite = sprite.convert("RGBA")
        scale = min(310 / max(1, sprite.width), 225 / max(1, sprite.height))
        sprite = sprite.resize(
            (max(1, round(sprite.width * scale)), max(1, round(sprite.height * scale))),
            Image.Resampling.LANCZOS,
        )
        frame = Image.new("RGBA", (320, 240), "black")
        frame.alpha_composite(sprite, ((320 - sprite.width) // 2, (240 - sprite.height) // 2))
        fade_start = math.floor((270 / 24) * FPS)
        if output_frame >= fade_start:
            alpha = min(1.0, (output_frame - fade_start) / max(1, frame_count - fade_start))
            frame = Image.blend(frame.convert("RGB"), Image.new("RGB", frame.size, "black"), alpha).convert("RGBA")
        process.stdin.write(frame.convert("RGB").tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg failed while rendering Stress Pico ending")
    target = temporary / "stress-pico-ending.mp4"
    subprocess.run([
        str(ffmpeg), "-y", "-loglevel", "error", "-i", str(silent), "-i", str(audio),
        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
        "-t", f"{frame_count / FPS:.6f}", str(target),
    ], check=True)
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ending-atlas", type=Path, required=True)
    parser.add_argument("--ending-audio", type=Path, required=True)
    parser.add_argument("--ending-out", type=Path, required=True)
    parser.add_argument("--psxavenc", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, default=Path("ffmpeg"))
    parser.add_argument("--header", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.source.is_file():
        raise RuntimeError(f"official Stress Pico Mix cutscene missing: {args.source}")
    if not args.ending_audio.is_file():
        raise RuntimeError(f"official Stress Pico Mix ending audio missing: {args.ending_audio}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.ending_out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        str(args.psxavenc), "-q", "-t", "str", "-v", "v2",
        "-f", "37800", "-b", "4", "-c", "2", "-s", "320x240",
        "-r", "15", "-x", "2", str(args.source), str(args.out),
    ], check=True)
    frames = encoded_frame_count(args.out)
    with tempfile.TemporaryDirectory() as directory:
        ending_source = build_ending(
            args.ending_atlas, args.ending_audio, args.ffmpeg, Path(directory)
        )
        subprocess.run([
            str(args.psxavenc), "-q", "-t", "str", "-v", "v2",
            "-f", "37800", "-b", "4", "-c", "2", "-s", "320x240",
            "-r", str(FPS), "-x", "2", str(ending_source), str(args.ending_out),
        ], check=True)
    ending_frames = encoded_frame_count(args.ending_out)
    args.header.parent.mkdir(parents=True, exist_ok=True)
    args.header.write_text(
        "#ifndef _PICO_MIX_MOVIES_GENERATED_H\n"
        "#define _PICO_MIX_MOVIES_GENERATED_H\n"
        f"#define PICO_STRESS_INTRO_FRAMES {frames}\n"
        f"#define PICO_STRESS_END_FRAMES {ending_frames}\n"
        "#endif\n"
    )
    report = {
        "policy": "official-v0.8.4-stress-pico-cutscene-only",
        "source": args.source.name,
        "file": args.out.name,
        "frames": frames,
        "bytes": args.out.stat().st_size,
        "ending": {
            "source": args.ending_atlas.name,
            "audio": args.ending_audio.name,
            "file": args.ending_out.name,
            "frames": ending_frames,
            "bytes": args.ending_out.stat().st_size,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
