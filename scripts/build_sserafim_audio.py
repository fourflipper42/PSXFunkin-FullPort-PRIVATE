#!/usr/bin/env python3
"""Recover official SPAGHETTI masters and encode correctly interleaved PS1 XA.

18.9 kHz 4-bit stereo XA requires eight physical sector slots per decoded
channel timeline. The previous two-way full/instrumental interleave delivered
each channel roughly four times too often and made the runtime's 75-sector/s
track length extend beyond SPAG.XA. This builder emits channels 0 and 1 plus
valid silent channels 2-7 so physical CD time and decoded audio time agree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

SECTOR = 2336
SAMPLE_RATE = 18900
INTERLEAVE_SLOTS = 8
OFFICIAL_STREAMS = {
    "Inst.ogg": 4_062_832,
    "Voices-sserafim-sakura.ogg": 4_125_963,
}


def run(command) -> None:
    subprocess.run([str(value) for value in command], check=True)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ogg_stream_length(data: bytes, start: int) -> int | None:
    offset = start
    while offset + 27 <= len(data) and data[offset:offset + 4] == b"OggS":
        segments = data[offset + 26]
        table_end = offset + 27 + segments
        if table_end > len(data):
            return None
        page_size = 27 + segments + sum(data[offset + 27:table_end])
        if offset + page_size > len(data):
            return None
        flags = data[offset + 5]
        offset += page_size
        if flags & 0x04:
            return offset - start
    return None


def extract_embedded_streams(executable: bytes) -> dict[str, bytes]:
    by_size: dict[int, list[bytes]] = {size: [] for size in OFFICIAL_STREAMS.values()}
    offset = 0
    while True:
        offset = executable.find(b"OggS", offset)
        if offset < 0:
            break
        length = ogg_stream_length(executable, offset)
        if length in by_size:
            by_size[length].append(executable[offset:offset + length])
        offset += 4
    result = {}
    for name, size in OFFICIAL_STREAMS.items():
        matches = by_size[size]
        if len(matches) != 1:
            raise RuntimeError(f"official embedded {name}: expected one {size}-byte Ogg, found {len(matches)}")
        result[name] = matches[0]
    return result


def encode_xa(encoder: Path, source: Path, target: Path, channel: int) -> None:
    run([
        encoder,
        "-q", "-t", "xa",
        "-f", str(SAMPLE_RATE), "-b", "4", "-c", "2",
        "-F", "1", "-C", str(channel),
        source, target,
    ])


def sectors(path: Path) -> list[bytes]:
    data = path.read_bytes()
    if not data or len(data) % SECTOR:
        raise RuntimeError(f"{path} is not {SECTOR}-byte sector aligned")
    return [data[index:index + SECTOR] for index in range(0, len(data), SECTOR)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--linux-zip", type=Path, required=True)
    parser.add_argument("--assets-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--psxavenc", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, default=Path("ffmpeg"))
    parser.add_argument("--ffprobe", type=Path, default=Path("ffprobe"))
    parser.add_argument("--header", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    with zipfile.ZipFile(args.linux_zip) as archive:
        executable = archive.read("Funkin")
    streams = extract_embedded_streams(executable)

    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        for name, data in streams.items():
            (temp / name).write_bytes(data)

        duration = float(subprocess.run(
            [str(args.ffprobe), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(temp / "Inst.ogg")],
            check=True, text=True, capture_output=True,
        ).stdout.strip())

        door1 = args.assets_root / "sserafim/sounds/doorKick1.ogg"
        door2 = args.assets_root / "sserafim/sounds/doorKick2.ogg"
        full_wav = temp / "spaghetti-full.wav"
        inst_wav = temp / "spaghetti-inst.wav"
        # Event times come from the official chart. Baking the door impacts into
        # both streams keeps them sample-accurate without interrupting CD-XA.
        run([
            args.ffmpeg, "-y", "-loglevel", "error",
            "-i", temp / "Inst.ogg", "-i", temp / "Voices-sserafim-sakura.ogg",
            "-i", door1, "-i", door2,
            "-filter_complex",
            "[2:a]adelay=1076|1076[k1];[3:a]adelay=2488|2488[k2];[0:a][1:a][k1][k2]amix=inputs=4:duration=longest:normalize=0[m]",
            "-map", "[m]", "-ar", str(SAMPLE_RATE), "-ac", "2", full_wav,
        ])
        run([
            args.ffmpeg, "-y", "-loglevel", "error",
            "-i", temp / "Inst.ogg", "-i", door1, "-i", door2,
            "-filter_complex",
            "[1:a]adelay=1076|1076[k1];[2:a]adelay=2488|2488[k2];[0:a][k1][k2]amix=inputs=3:duration=longest:normalize=0[m]",
            "-map", "[m]", "-ar", str(SAMPLE_RATE), "-ac", "2", inst_wav,
        ])

        full_xa = temp / "full.xa"
        inst_xa = temp / "inst.xa"
        encode_xa(args.psxavenc, full_wav, full_xa, 0)
        encode_xa(args.psxavenc, inst_wav, inst_xa, 1)
        full_sectors = sectors(full_xa)
        inst_sectors = sectors(inst_xa)

        silence_wav = temp / "silence.wav"
        run([
            args.ffmpeg,
            "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=stereo",
            "-t", "1", silence_wav,
        ])
        silence: dict[int, bytes] = {}
        for channel in range(INTERLEAVE_SLOTS):
            silent_xa = temp / f"silence-{channel}.xa"
            encode_xa(args.psxavenc, silence_wav, silent_xa, channel)
            silence[channel] = sectors(silent_xa)[0]

        count = max(len(full_sectors), len(inst_sectors))
        output = bytearray()
        for index in range(count):
            output += full_sectors[index] if index < len(full_sectors) else silence[0]
            output += inst_sectors[index] if index < len(inst_sectors) else silence[1]
            for channel in range(2, INTERLEAVE_SLOTS):
                output += silence[channel]
        target = args.out / "spag.xa"
        target.write_bytes(output)

    centiseconds = max(1, round(duration * 100.0))
    physical_sectors = (args.out / "spag.xa").stat().st_size // SECTOR
    expected_sectors = count * INTERLEAVE_SLOTS
    if physical_sectors != expected_sectors:
        raise RuntimeError(f"SPAG XA interleave mismatch: {physical_sectors} != {expected_sectors}")
    # The runtime measures XA track boundaries in physical 75 Hz CD sectors.
    # Allow normal encoder rounding, but reject the old under-interleaved layout.
    expected_from_duration = duration * 75.0
    if not (expected_from_duration * 0.96 <= physical_sectors <= expected_from_duration * 1.04 + INTERLEAVE_SLOTS):
        raise RuntimeError(
            f"SPAG XA physical duration mismatch: sectors={physical_sectors}, duration={duration:.3f}s"
        )

    args.header.parent.mkdir(parents=True, exist_ok=True)
    args.header.write_text(
        "#ifndef _SSERAFIM_AUDIO_GENERATED_H\n"
        "#define _SSERAFIM_AUDIO_GENERATED_H\n"
        f"#define SSERAFIM_XA_CENTISECONDS {centiseconds}\n"
        "#endif\n"
    )
    report = {
        "policy": "official-v0.8.4-linux-embedded-spaghetti-masters",
        "official_linux_executable_sha256": sha256(executable),
        "streams": {
            name: {"bytes": len(data), "sha256": sha256(data)} for name, data in streams.items()
        },
        "duration_seconds": duration,
        "centiseconds": centiseconds,
        "door_kicks_baked_at_ms": [1076, 2488],
        "xa": {
            "file": "spag.xa",
            "bytes": (args.out / "spag.xa").stat().st_size,
            "physical_sectors": physical_sectors,
            "logical_timeline_sectors": count,
            "interleave_slots": INTERLEAVE_SLOTS,
            "physical_seconds": physical_sectors / 75.0,
            "channels": {"0": "full mix", "1": "instrumental", "2-7": "silent padding"},
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
