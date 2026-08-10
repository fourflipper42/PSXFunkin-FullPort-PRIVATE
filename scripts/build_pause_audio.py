#!/usr/bin/env python3
"""Encode the official Funkin Breakfast pause music as a PS1 XA stream."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path


SAMPLE_RATE = 18900


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_breakfast(root: Path) -> Path:
    candidates = [path for path in root.rglob("breakfast.ogg") if path.is_file()]
    if not candidates:
        raise SystemExit(f"official breakfast.ogg missing below {root}")

    def rank(path: Path) -> tuple[int, int, str]:
        normalized = path.as_posix().lower()
        if normalized.endswith("/shared/music/breakfast.ogg"):
            priority = 0
        elif normalized.endswith("/music/breakfast.ogg"):
            priority = 1
        else:
            priority = 2
        return priority, len(path.parts), normalized

    return sorted(candidates, key=rank)[0]


def run(command: list[object]) -> None:
    subprocess.run([str(value) for value in command], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--psxavenc", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, default=Path("ffmpeg"))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--font-template", type=Path, required=True)
    parser.add_argument("--font-out", type=Path, required=True)
    args = parser.parse_args()

    source = find_breakfast(args.assets_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        wav = Path(temp_dir) / "breakfast.wav"
        run([
            args.ffmpeg,
            "-y", "-loglevel", "error",
            "-i", source,
            "-ar", str(SAMPLE_RATE),
            "-ac", "2",
            wav,
        ])
        run([
            args.psxavenc,
            "-q",
            "-t", "xa",
            "-f", str(SAMPLE_RATE),
            "-b", "4",
            "-c", "2",
            "-F", "1",
            "-C", "0",
            wav,
            args.out,
        ])

    if not args.out.is_file() or args.out.stat().st_size == 0:
        raise SystemExit("pause XA encoder produced no output")
    if args.out.stat().st_size % 2336:
        raise SystemExit("pause XA is not aligned to raw XA sectors")

    font = bytearray(args.font_template.read_bytes())
    if len(font) < 32 or struct.unpack_from("<I", font, 0)[0] != 0x10:
        raise SystemExit("pause font template is not a TIM")
    flags = struct.unpack_from("<I", font, 4)[0]
    if (flags & 7) != 0 or not (flags & 8):
        raise SystemExit("pause font template must be a 4bpp CLUT TIM")
    clut_x, clut_y, clut_w, clut_h = struct.unpack_from("<4H", font, 12)
    if (clut_x, clut_y, clut_w, clut_h) != (0, 511, 16, 1):
        raise SystemExit(f"unexpected bold font CLUT {(clut_x, clut_y, clut_w, clut_h)}")
    struct.pack_into("<2H", font, 12, 256, 511)
    args.font_out.parent.mkdir(parents=True, exist_ok=True)
    args.font_out.write_bytes(font)

    report = {
        "policy": "official-v0.8.4-breakfast-audio-only",
        "source": str(source.relative_to(args.assets_root)),
        "source_bytes": source.stat().st_size,
        "source_sha256": sha256(source),
        "sample_rate": SAMPLE_RATE,
        "channels": 2,
        "xa_file": args.out.name,
        "xa_bytes": args.out.stat().st_size,
        "xa_sectors": args.out.stat().st_size // 2336,
        "xa_sha256": sha256(args.out),
        "pause_font": {
            "template": str(args.font_template),
            "file": args.font_out.name,
            "bytes": args.font_out.stat().st_size,
            "sha256": sha256(args.font_out),
            "clut": [256, 511, 16, 1],
            "policy": "boldfont pixels unchanged; CLUT relocated away from stage HUD0",
        },
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

# CI retrigger after correcting the Pico Makefile source continuation generator.
# Production rebuild after correcting the Pico stagedef separator generator.
