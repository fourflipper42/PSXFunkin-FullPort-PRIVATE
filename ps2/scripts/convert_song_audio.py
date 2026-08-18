#!/usr/bin/env python3
"""Convert FNF song OGGs into PS2-friendly raw PCM streams.

The PS2 runtime deliberately does not decode OGG. DVD capacity is large enough
that decoding once at build time is simpler, more reliable, and gives the
runtime precise sample-count timing.

For each directory containing Inst.ogg this script writes:
  <same relative directory>/inst.pcm
  <same relative directory>/voices.pcm  (when one or more Voices*.ogg exist)

Multiple modern FNF vocal stems are mixed into one vocals stream at build time.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

RATE = 48_000
CHANNELS = 2
BITS = 16
FRAME_BYTES = CHANNELS * (BITS // 8)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ffmpeg_base(ffmpeg: str) -> list[str]:
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]


def convert_one(ffmpeg: str, src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(
        ffmpeg_base(ffmpeg)
        + [
            "-i",
            str(src),
            "-vn",
            "-ar",
            str(RATE),
            "-ac",
            str(CHANNELS),
            "-f",
            "s16le",
            str(dst),
        ]
    )


def convert_vocals(ffmpeg: str, stems: list[Path], dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if len(stems) == 1:
        convert_one(ffmpeg, stems[0], dst)
        return

    cmd = ffmpeg_base(ffmpeg)
    for stem in stems:
        cmd += ["-i", str(stem)]

    inputs = "".join(f"[{i}:a]" for i in range(len(stems)))
    filt = f"{inputs}amix=inputs={len(stems)}:duration=longest:normalize=0[v]"
    cmd += [
        "-filter_complex",
        filt,
        "-map",
        "[v]",
        "-ar",
        str(RATE),
        "-ac",
        str(CHANNELS),
        "-f",
        "s16le",
        str(dst),
    ]
    run(cmd)


def find_case_insensitive(directory: Path, exact_name: str) -> Path | None:
    target = exact_name.lower()
    for child in directory.iterdir():
        if child.is_file() and child.name.lower() == target:
            return child
    return None


def vocal_stems(directory: Path) -> list[Path]:
    return sorted(
        (
            child
            for child in directory.iterdir()
            if child.is_file()
            and child.suffix.lower() == ".ogg"
            and child.stem.lower().startswith("voices")
        ),
        key=lambda p: p.name.lower(),
    )


def describe_pcm(path: Path | None) -> dict | None:
    if path is None or not path.exists():
        return None
    size = path.stat().st_size
    frames = size // FRAME_BYTES
    return {
        "bytes": size,
        "frames": frames,
        "seconds": frames / RATE,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_root", type=Path, help="Root containing FNF song folders")
    parser.add_argument("output_root", type=Path, help="PS2 audio output root")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()

    ffmpeg = shutil.which(args.ffmpeg) if Path(args.ffmpeg).name == args.ffmpeg else args.ffmpeg
    if not ffmpeg or not Path(ffmpeg).exists():
        raise SystemExit(f"ffmpeg not found: {args.ffmpeg}")

    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    song_dirs: list[Path] = []
    for candidate in input_root.rglob("*"):
        if candidate.is_dir() and find_case_insensitive(candidate, "Inst.ogg") is not None:
            song_dirs.append(candidate)

    manifest: dict = {
        "format": {
            "sample_rate": RATE,
            "channels": CHANNELS,
            "bits": BITS,
            "frame_bytes": FRAME_BYTES,
            "encoding": "signed 16-bit little-endian PCM",
        },
        "songs": [],
    }

    for song_dir in sorted(song_dirs):
        rel = song_dir.relative_to(input_root)
        out_dir = output_root / rel
        inst_src = find_case_insensitive(song_dir, "Inst.ogg")
        assert inst_src is not None
        stems = vocal_stems(song_dir)

        inst_dst = out_dir / "inst.pcm"
        voices_dst = out_dir / "voices.pcm" if stems else None

        print(f"[PS2 audio] {rel}")
        convert_one(ffmpeg, inst_src, inst_dst)
        if voices_dst is not None:
            convert_vocals(ffmpeg, stems, voices_dst)

        manifest["songs"].append(
            {
                "id": rel.as_posix(),
                "inst": str(inst_dst.relative_to(output_root).as_posix()),
                "voices": (
                    str(voices_dst.relative_to(output_root).as_posix())
                    if voices_dst is not None
                    else None
                ),
                "source_vocal_stems": [stem.name for stem in stems],
                "inst_info": describe_pcm(inst_dst),
                "voices_info": describe_pcm(voices_dst),
            }
        )

    manifest_path = args.manifest or (output_root / "audio_manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"converted {len(manifest['songs'])} songs")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
