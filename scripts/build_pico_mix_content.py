#!/usr/bin/env python3
"""Build all official v0.8.4 Pico Mix charts, events, and CD-XA audio."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import math
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

SECTOR = 2336
SONGS = (
    "bopeebo", "fresh", "dadbattle", "spookeez", "south",
    "pico", "philly-nice", "blammed", "cocoa", "eggnog",
    "senpai", "roses", "ugh", "guns", "stress",
)
DISPLAY = {
    "bopeebo": "BOPEEBO", "fresh": "FRESH", "dadbattle": "DADBATTLE",
    "spookeez": "SPOOKEEZ", "south": "SOUTH", "pico": "PICO",
    "philly-nice": "PHILLY NICE", "blammed": "BLAMMED", "cocoa": "COCOA",
    "eggnog": "EGGNOG", "senpai": "SENPAI", "roses": "ROSES",
    "ugh": "UGH", "guns": "GUNS", "stress": "STRESS",
}
EVENT_KIND = {
    "FocusCamera": 1, "ZoomCamera": 2, "SetCameraBop": 3,
    "ScrollSpeed": 4, "PlayAnimation": 5, "EnableMask": 6,
    "SetHealthIcon": 7,
}
EASE_KIND = {
    "classic": 0, "instant": 0, "expoout": 1, "expoinout": 1,
    "quadinout": 2, "quartout": 3, "circout": 4,
    "cubeinout": 5, "quartinout": 6, "": 7, "linear": 7,
}
PLAYER_ANIMS = {
    "hey": 1, "cheer": 2, "burpshit": 3, "burpsmile": 4,
    "burpsmilelong": 4, "shit": 5, "knifetoss": 6,
}
OPPONENT_ANIMS = {
    "ugh": 1, "augh": 1, "laugh": 2, "beat it": 2,
    "hehprettygood": 3, "redheadsanim": 4,
}


def load_chartc():
    path = Path(__file__).with_name("psxfunkin_chartc_weekend1.py")
    spec = importlib.util.spec_from_file_location("pico_mix_chartc", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(command) -> None:
    subprocess.run([str(value) for value in command], check=True)


def encode(encoder: Path, source: Path, target: Path, channel: int) -> None:
    run([encoder, "-q", "-t", "xa", "-f", "18900", "-b", "4", "-c", "2",
         "-F", "1", "-C", str(channel), source, target])


def sectors(path: Path) -> list[bytes]:
    data = path.read_bytes()
    if len(data) % SECTOR:
        raise RuntimeError(f"{path} is not {SECTOR}-byte sector aligned")
    return [data[offset:offset + SECTOR] for offset in range(0, len(data), SECTOR)]


def mix_song(ffmpeg: Path, song_dir: Path, voices: list[str], target: Path) -> None:
    inputs = [song_dir / "Inst-pico.ogg"] + [song_dir / voice for voice in voices]
    for source in inputs:
        if not source.is_file():
            raise RuntimeError(f"official Pico Mix audio missing: {source}")
    command = [ffmpeg, "-y", "-loglevel", "error"]
    for source in inputs:
        command += ["-i", source]
    labels = "".join(f"[{index}:a]" for index in range(len(inputs)))
    command += [
        "-filter_complex", f"{labels}amix=inputs={len(inputs)}:duration=longest:normalize=0[m]",
        "-map", "[m]", "-ar", "18900", "-ac", "2", target,
    ]
    run(command)


def pico_voice_files(metadata: dict) -> list[str]:
    characters = metadata["playData"]["characters"]
    result = []
    for key in ("opponentVocals", "playerVocals"):
        for character in characters.get(key, []):
            name = f"Voices-{character}-pico.ogg"
            if name not in result:
                result.append(name)
    return result


def event_row(song_index: int, event: dict, changes, chartc) -> tuple[int, ...] | None:
    name = event.get("e")
    if name not in EVENT_KIND:
        return None
    value = event.get("v") or {}
    step = chartc.round_half_up(chartc.time_to_beat(float(event.get("t", 0)), changes) * 4.0)
    kind = EVENT_KIND[name]
    flags = 0
    a = b = c = 0
    ease_name = str(value.get("ease", ""))
    if value.get("easeDir"):
        ease_name += str(value["easeDir"])
    ease_key = ease_name.replace("_", "").replace("-", "").lower()
    # FocusCamera uniquely defaults to CLASSIC (the normal follow camera),
    # whereas every other tween event defaults to linear.
    ease = EASE_KIND.get(ease_key, 0 if name == "FocusCamera" else 7)
    if name == "FocusCamera" and not ease_key:
        ease = 0
    duration = max(0, min(32767, round(float(value.get("duration", 0)))))
    if name == "FocusCamera":
        flags = (int(value.get("char", 0)) & 3) | (ease << 2)
        a = round(float(value.get("x", 0)) * 0.20)
        b = round(float(value.get("y", 0)) * 0.20)
        c = duration
    elif name == "ZoomCamera":
        a = max(1, min(32767, round(float(value.get("zoom", 1.0)) * 1024.0)))
        b = duration
        c = ease
    elif name == "SetCameraBop":
        # The official event expresses rate/offset in beats. The PS1 runtime
        # indexes events in steps, and Funkin's camera multiplier is
        # 1 + (0.015 * intensity).
        a = max(0, min(32767, round(float(value.get("rate", 4)) * 4.0)))
        intensity = float(value.get("intensity", 1.0))
        b = max(1, min(32767, round((1.0 + 0.015 * intensity) * 1024.0)))
        c = max(-32768, min(32767, round(float(value.get("offset", 0)) * 4.0)))
    elif name == "ScrollSpeed":
        flags = 1 if bool(value.get("absolute", False)) else 0
        a = max(1, min(32767, round(float(value.get("scroll", 1.0)) * 1024.0)))
        b = duration
        c = ease
    elif name == "PlayAnimation":
        target = str(value.get("target", "boyfriend")).lower()
        animation = str(value.get("anim", "")).replace(" ", "").lower()
        if target in {"boyfriend", "bf", "player"}:
            a = PLAYER_ANIMS.get(animation, 0)
        else:
            flags = 1
            # Opponent keys intentionally retain spaces for "beat it".
            raw = str(value.get("anim", "")).strip().lower()
            a = OPPONENT_ANIMS.get(raw, OPPONENT_ANIMS.get(animation, 0))
        if a == 0:
            return None
    elif name == "SetHealthIcon":
        flags = int(value.get("char", 1)) & 1
        a = 1
    return song_index, step, kind, flags, a, b, c


def write_event_header(path: Path, rows: list[tuple[int, ...]]) -> None:
    starts = []
    counts = []
    for song_index in range(len(SONGS)):
        positions = [index for index, row in enumerate(rows) if row[0] == song_index]
        starts.append(positions[0] if positions else 0)
        counts.append(len(positions))
    lines = [
        "#ifndef _PICO_MIX_EVENTS_GENERATED_H", "#define _PICO_MIX_EVENTS_GENERATED_H", "",
        "static const PicoMixEvent pico_mix_events[] = {",
    ]
    for song, step, kind, flags, a, b, c in rows:
        lines.append(f"    {{{step}, {kind}, {flags}, {a}, {b}, {c}}}, // {song}: {SONGS[song]}")
    lines += [
        "};",
        "static const u16 pico_mix_event_start[] = {" + ",".join(map(str, starts)) + "};",
        "static const u16 pico_mix_event_count[] = {" + ",".join(map(str, counts)) + "};",
        f"#define PICO_MIX_EVENT_TOTAL {len(rows)}", "#endif", "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def write_audio_header(path: Path, durations: list[int]) -> None:
    lines = ["#ifndef _PICO_MIX_AUDIO_GENERATED_H", "#define _PICO_MIX_AUDIO_GENERATED_H"]
    for index, duration in enumerate(durations):
        lines.append(f"#define PICO_MIX_LENGTH_{index} {duration}")
    lines += ["#endif", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)

    # Current direct interface.
    parser.add_argument("--iso-root", type=Path)
    parser.add_argument("--psxavenc", type=Path)
    parser.add_argument("--ffmpeg", type=Path, default=Path("ffmpeg"))
    parser.add_argument("--ffprobe", type=Path, default=Path("ffprobe"))
    parser.add_argument("--event-header", type=Path)
    parser.add_argument("--audio-header", type=Path)
    parser.add_argument("--report", type=Path)

    # Compatibility interface used by the full-port-completion workflow.
    # Keep this deterministic so the CI pipeline and direct script interface
    # cannot silently drift apart again.
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--encoder", type=Path)
    parser.add_argument("--pico-mix-report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.iso_root is None and args.upstream is not None:
        args.iso_root = args.upstream / "iso"
    if args.psxavenc is None:
        args.psxavenc = args.encoder
    if args.event_header is None and args.upstream is not None:
        args.event_header = args.upstream / "src/pico_mix_events_generated.h"
    if args.audio_header is None and args.upstream is not None:
        args.audio_header = args.upstream / "src/pico_mix_audio_generated.h"
    if args.report is None:
        args.report = args.output

    missing = [
        name for name, value in (
            ("--iso-root/--upstream", args.iso_root),
            ("--psxavenc/--encoder", args.psxavenc),
            ("--event-header", args.event_header),
            ("--audio-header", args.audio_header),
            ("--report/--output", args.report),
        ) if value is None
    ]
    if missing:
        parser.error("missing required Pico content destinations: " + ", ".join(missing))

    chartc = load_chartc()
    chart_out = args.iso_root / "chart"
    music_out = args.iso_root / "music"
    chart_out.mkdir(parents=True, exist_ok=True)
    music_out.mkdir(parents=True, exist_ok=True)

    chart_records = []
    event_rows = []
    metadata_rows = []
    durations = []
    for song_index, song in enumerate(SONGS):
        data_dir = args.root / "data/songs" / song
        chart = json.loads((data_dir / f"{song}-chart-pico.json").read_text())
        metadata = json.loads((data_dir / f"{song}-metadata-pico.json").read_text())
        for difficulty, suffix in (("easy", "e"), ("normal", "n"), ("hard", "h")):
            # Parents Christmas routes Mom notes through the engine's existing
            # alternate animation slots. Official noanim notes deliberately
            # suppress character animation while retaining timing/scoring.
            chart_for_ps1 = copy.deepcopy(chart)
            for note in chart_for_ps1["notes"][difficulty]:
                if str(note.get("k", "")).lower() == "mom":
                    note["alt"] = True
            payload = chartc.convert(
                chart_for_ps1, metadata, difficulty,
                kind_codes={"noanim": 50, "censor": 51, "mom": 52},
            )
            target = chart_out / f"10.{song_index + 1}{suffix}.cht"
            target.write_bytes(payload)
            chart_records.append({"song": song, "difficulty": difficulty, "file": target.name, "bytes": len(payload)})
        changes = chartc.read_time_changes(metadata)
        rows = [row for event in chart.get("events", []) if (row := event_row(song_index, event, changes, chartc))]
        rows.sort(key=lambda row: row[1])
        event_rows.extend(rows)
        voices = pico_voice_files(metadata)
        metadata_rows.append({
            "song": song, "display": DISPLAY[song], "bpm": round(changes[0].bpm),
            "voices": voices, "events": len(rows),
        })

    write_event_header(args.event_header, event_rows)

    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        silence_wav = temp / "silence.wav"
        run([args.ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
             "anullsrc=r=18900:cl=stereo", "-t", "1", silence_wav])
        silent = []
        for channel in range(8):
            target = temp / f"silence-{channel}.xa"
            encode(args.psxavenc, silence_wav, target, channel)
            silent.append(sectors(target)[0])

        encoded: dict[int, tuple[Path, Path]] = {}
        for song_index, record in enumerate(metadata_rows):
            song = record["song"]
            song_dir = args.root / "songs" / song
            full_wav = temp / f"{song}-full.wav"
            inst_wav = temp / f"{song}-inst.wav"
            mix_song(args.ffmpeg, song_dir, record["voices"], full_wav)
            run([args.ffmpeg, "-y", "-loglevel", "error", "-i", song_dir / "Inst-pico.ogg",
                 "-ar", "18900", "-ac", "2", inst_wav])
            duration = float(subprocess.run([
                str(args.ffprobe), "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1", str(song_dir / "Inst-pico.ogg"),
            ], check=True, text=True, capture_output=True).stdout.strip())
            durations.append(max(1, round(duration * 100.0)))
            channel = (song_index % 4) * 2
            full_xa = temp / f"{song}-full.xa"
            inst_xa = temp / f"{song}-inst.xa"
            encode(args.psxavenc, full_wav, full_xa, channel)
            encode(args.psxavenc, inst_wav, inst_xa, channel + 1)
            encoded[song_index] = (full_xa, inst_xa)

        audio_records = []
        for group in range(4):
            streams: list[list[bytes] | None] = [None] * 8
            for local in range(4):
                song_index = group * 4 + local
                if song_index >= len(SONGS):
                    continue
                full_xa, inst_xa = encoded[song_index]
                streams[local * 2] = sectors(full_xa)
                streams[local * 2 + 1] = sectors(inst_xa)
            count = max(len(stream) for stream in streams if stream is not None)
            output = bytearray()
            for sector_index in range(count):
                for channel, stream in enumerate(streams):
                    output += stream[sector_index] if stream is not None and sector_index < len(stream) else silent[channel]
            target = music_out / f"picomix{group}.xa"
            target.write_bytes(output)
            audio_records.append({"file": target.name, "bytes": target.stat().st_size, "physical_sectors": len(output) // SECTOR})

    write_audio_header(args.audio_header, durations)
    report = {
        "policy": "official-v0.8.4-pico-mix-charts-events-and-audio-only",
        "songs": metadata_rows,
        "charts": chart_records,
        "events": {"total": len(event_rows), "supported_kinds": EVENT_KIND},
        "durations_centiseconds": durations,
        "audio": audio_records,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
