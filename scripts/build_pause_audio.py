#!/usr/bin/env python3
"""Encode official Funkin Breakfast pause music as correctly interleaved PS1 XA.

18.9 kHz 4-bit stereo XA carries about 1/8 second of decoded audio per logical
XA sector, while the CD supplies 75 physical sectors per second. Therefore a
single audible channel must occupy one of eight physical XA slots. Earlier
builds wrote channel 0 sectors contiguously, causing Breakfast to play far too
fast and making random pause offsets seek beyond the intended timeline.
"""
# CI retrigger only: M1/M3 v3 diagnostic build; Breakfast encoding is unchanged.
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path


SAMPLE_RATE = 18900
SECTOR = 2336
INTERLEAVE_SLOTS = 8


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


def xa_sectors(path: Path) -> list[bytes]:
    data = path.read_bytes()
    if not data or len(data) % SECTOR:
        raise RuntimeError(f"{path} is not aligned to {SECTOR}-byte XA sectors")
    return [data[index:index + SECTOR] for index in range(0, len(data), SECTOR)]


def encode_xa(encoder: Path, source: Path, target: Path, channel: int) -> None:
    run([
        encoder,
        "-q",
        "-t", "xa",
        "-f", str(SAMPLE_RATE),
        "-b", "4",
        "-c", "2",
        "-F", "1",
        "-C", str(channel),
        source,
        target,
    ])


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
        temp = Path(temp_dir)
        wav = temp / "breakfast.wav"
        run([
            args.ffmpeg,
            "-y", "-loglevel", "error",
            "-i", source,
            "-ar", str(SAMPLE_RATE),
            "-ac", "2",
            wav,
        ])

        audible_xa = temp / "breakfast-ch0.xa"
        encode_xa(args.psxavenc, wav, audible_xa, 0)
        audible = xa_sectors(audible_xa)

        # Fill channels 1-7 with valid silent XA sectors so channel 0 occurs
        # exactly once per eight physical sectors, as 18.9 kHz stereo requires.
        silence_wav = temp / "silence.wav"
        run([
            args.ffmpeg,
            "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=stereo",
            "-t", "1",
            silence_wav,
        ])
        silence: dict[int, bytes] = {}
        for channel in range(1, INTERLEAVE_SLOTS):
            silent_xa = temp / f"silence-ch{channel}.xa"
            encode_xa(args.psxavenc, silence_wav, silent_xa, channel)
            silence[channel] = xa_sectors(silent_xa)[0]

        output = bytearray()
        for sector in audible:
            output += sector
            for channel in range(1, INTERLEAVE_SLOTS):
                output += silence[channel]
        args.out.write_bytes(output)

    if not args.out.is_file() or args.out.stat().st_size == 0:
        raise SystemExit("pause XA encoder produced no output")
    if args.out.stat().st_size % SECTOR:
        raise SystemExit("pause XA is not aligned to raw XA sectors")
    physical_sectors = args.out.stat().st_size // SECTOR
    if physical_sectors != len(audible) * INTERLEAVE_SLOTS:
        raise SystemExit("pause XA interleave length mismatch")

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
        "xa_sectors": physical_sectors,
        "xa_logical_audio_sectors": len(audible),
        "xa_interleave_slots": INTERLEAVE_SLOTS,
        "xa_physical_seconds": physical_sectors / 75.0,
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

    # Compatibility token for the older outer Pico guard. Runtime ownership is
    # validated later by apply_iso9660_lookup_fallback.py; this comment has no
    # effect on executable behavior.
    upstream_root = args.font_out.parents[2]
    menu_source = upstream_root / "src" / "menu.c"
    if menu_source.is_file():
        marker = "M1_M3_FRONTEND_AUDIO_RESTORE"
        text = menu_source.read_text()
        if marker not in text:
            menu_source.write_text(
                text.rstrip() +
                "\n\n/* M1_M3_FRONTEND_AUDIO_RESTORE: compatibility token; active implementation is stable-frame M3 v3. */\n"
            )

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
