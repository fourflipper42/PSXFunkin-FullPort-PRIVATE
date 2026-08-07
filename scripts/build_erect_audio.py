#!/usr/bin/env python3
"""Build official v0.8.4 Erect remix XA groups for PSXFunkin.

Each song uses two XA channels: even = full remix, odd = instrumental only.
Four songs are packed into each 8-channel 18.9 kHz XA file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

SECTOR = 2336
SAMPLE_RATE = 18900

GROUPS = [
    ("erecta.xa", ["bopeebo", "fresh", "dadbattle", "spookeez"]),
    ("erectb.xa", ["south", "pico", "philly-nice", "blammed"]),
    ("erectc.xa", ["satin-panties", "high", "cocoa", "eggnog"]),
    ("erectd.xa", ["senpai", "roses", "thorns", "ugh"]),
]

MACRO_NAMES = {
    "bopeebo": "BOPEEBO",
    "fresh": "FRESH",
    "dadbattle": "DADBATTLE",
    "spookeez": "SPOOKEEZ",
    "south": "SOUTH",
    "pico": "PICO",
    "philly-nice": "PHILLY",
    "blammed": "BLAMMED",
    "satin-panties": "SATINPANTIES",
    "high": "HIGH",
    "cocoa": "COCOA",
    "eggnog": "EGGNOG",
    "senpai": "SENPAI",
    "roses": "ROSES",
    "thorns": "THORNS",
    "ugh": "UGH",
}


def run(cmd: list[object]) -> None:
    subprocess.run([str(x) for x in cmd], check=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def xa_sectors(path: Path) -> list[bytes]:
    data = path.read_bytes()
    if len(data) % SECTOR:
        raise ValueError(f"{path} is not aligned to {SECTOR}-byte XA sectors")
    return [data[i : i + SECTOR] for i in range(0, len(data), SECTOR)]


def encode_xa(enc: Path, wav: Path, out: Path, channel: int) -> None:
    run([
        enc,
        "-q",
        "-t", "xa",
        "-f", str(SAMPLE_RATE),
        "-b", "4",
        "-c", "2",
        "-F", "1",
        "-C", str(channel),
        wav,
        out,
    ])


def find_erect_voices(song_dir: Path) -> list[Path]:
    voices = []
    for p in song_dir.iterdir():
        name = p.name.lower()
        if p.is_file() and name.startswith("voices") and name.endswith("-erect.ogg"):
            voices.append(p)
    return sorted(voices, key=lambda p: p.name.lower())


def make_full_mix(ffmpeg: Path, inst: Path, voices: list[Path], out: Path) -> None:
    if not voices:
        run([ffmpeg, "-y", "-loglevel", "error", "-i", inst, "-ar", str(SAMPLE_RATE), "-ac", "2", out])
        return

    cmd: list[object] = [ffmpeg, "-y", "-loglevel", "error", "-i", inst]
    for voice in voices:
        cmd += ["-i", voice]
    count = 1 + len(voices)
    inputs = "".join(f"[{i}:a]" for i in range(count))
    cmd += [
        "-filter_complex",
        f"{inputs}amix=inputs={count}:duration=longest:normalize=0[a]",
        "-map", "[a]",
        "-ar", str(SAMPLE_RATE),
        "-ac", "2",
        out,
    ]
    run(cmd)


def make_inst(ffmpeg: Path, inst: Path, out: Path) -> None:
    run([ffmpeg, "-y", "-loglevel", "error", "-i", inst, "-ar", str(SAMPLE_RATE), "-ac", "2", out])


def interleave_group(out: Path, streams: list[Path], silence_sector: list[bytes]) -> int:
    encoded = [xa_sectors(p) for p in streams]
    longest = max(len(s) for s in encoded)
    data = bytearray()
    for index in range(longest):
        for channel, stream in enumerate(encoded):
            data += stream[index] if index < len(stream) else silence_sector[channel]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return longest * 8


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True, help="Extracted official asset root")
    ap.add_argument("--out", type=Path, required=True, help="upstream/iso/music")
    ap.add_argument("--psxavenc", type=Path, required=True)
    ap.add_argument("--ffmpeg", type=Path, default=Path("ffmpeg"))
    ap.add_argument("--header", type=Path, required=True, help="Generated C header path")
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    songs_root = args.root / "songs"
    if not songs_root.is_dir():
        raise SystemExit(f"missing songs directory: {songs_root}")

    args.out.mkdir(parents=True, exist_ok=True)
    args.header.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, object] = {
        "sample_rate": SAMPLE_RATE,
        "sector_bytes": SECTOR,
        "groups": {},
        "songs": {},
    }
    track_physical_sectors: dict[str, int] = {}

    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)

        silent_wav = temp / "silence.wav"
        run([
            args.ffmpeg,
            "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=stereo",
            "-t", "1",
            silent_wav,
        ])
        silence_sector: list[bytes] = []
        for channel in range(8):
            silent_xa = temp / f"silence-{channel}.xa"
            encode_xa(args.psxavenc, silent_wav, silent_xa, channel)
            silence_sector.append(xa_sectors(silent_xa)[0])

        for group_name, songs in GROUPS:
            streams: list[Path] = [Path()] * 8
            group_info: dict[str, object] = {"songs": [], "channels": {}}

            for slot, song in enumerate(songs):
                base_channel = slot * 2
                song_dir = songs_root / song
                inst = song_dir / "Inst-erect.ogg"
                if not inst.is_file():
                    raise SystemExit(f"missing official Erect instrumental: {inst}")
                voices = find_erect_voices(song_dir)

                full_wav = temp / f"{song}-full.wav"
                inst_wav = temp / f"{song}-inst.wav"
                full_xa = temp / f"{song}-full.xa"
                inst_xa = temp / f"{song}-inst.xa"

                make_full_mix(args.ffmpeg, inst, voices, full_wav)
                make_inst(args.ffmpeg, inst, inst_wav)
                encode_xa(args.psxavenc, full_wav, full_xa, base_channel)
                encode_xa(args.psxavenc, inst_wav, inst_xa, base_channel + 1)

                full_count = len(xa_sectors(full_xa))
                inst_count = len(xa_sectors(inst_xa))
                physical_count = max(full_count, inst_count) * 8
                track_physical_sectors[song] = physical_count

                streams[base_channel] = full_xa
                streams[base_channel + 1] = inst_xa
                group_info["songs"].append(song)
                group_info["channels"][song] = {
                    "full": base_channel,
                    "instrumental": base_channel + 1,
                }
                report["songs"][song] = {
                    "group": group_name,
                    "full_channel": base_channel,
                    "instrumental_channel": base_channel + 1,
                    "instrumental": str(inst.relative_to(args.root)),
                    "voices": [str(p.relative_to(args.root)) for p in voices],
                    "full_encoded_sectors": full_count,
                    "instrumental_encoded_sectors": inst_count,
                    "track_physical_sectors": physical_count,
                }

            out = args.out / group_name
            physical_sectors = interleave_group(out, streams, silence_sector)
            group_info.update({
                "physical_sectors": physical_sectors,
                "bytes": out.stat().st_size,
                "sha256": sha256(out),
            })
            report["groups"][group_name] = group_info

    header_lines = [
        "#ifndef _ERECT_AUDIO_GENERATED_H",
        "#define _ERECT_AUDIO_GENERATED_H",
        "",
        "// Generated by scripts/build_erect_audio.py from official v0.8.4 audio.",
    ]
    for song, macro in MACRO_NAMES.items():
        header_lines.append(f"#define ERECT_{macro}_SECTORS {track_physical_sectors[song]}")
    header_lines += ["", "#endif", ""]
    args.header.write_text("\n".join(header_lines))

    report["header"] = str(args.header)
    report["header_sha256"] = sha256(args.header)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
