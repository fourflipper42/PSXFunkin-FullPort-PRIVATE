#!/usr/bin/env python3
"""Build all official SPAGHETTI charts and a complete PS1 event stream."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

KIND_CODES = {
    "sakura-joint": 40,
    "sakura-bf1": 41,
    "sakura-bf2": 42,
}

EVENT_KIND = {
    "FocusCamera": 1,
    "ZoomCamera": 2,
    "SetCameraBop": 3,
    "sserafimShow": 4,
    "sserafimSing": 5,
    "sserafimDark": 6,
    "sserafimLights": 7,
    "sserafimCover": 8,
    "sserafimFlash": 9,
    "sserafimPulseLights": 10,
    "sserafimKick": 11,
    "sserafimBeautiful": 12,
    "sserafimEnd": 13,
    "sserafimGuitarVibration": 14,
    "SetHealthIcon": 15,
}

ICON_IDS = {
    "bf": 0,
    "gf": 1,
    "yunjin": 2,
    "kazuha": 3,
    "chaewon": 4,
    "eunchae": 5,
    "sakura": 6,
}


def load_chartc():
    path = Path(__file__).with_name("psxfunkin_chartc_weekend1.py")
    spec = importlib.util.spec_from_file_location("sserafim_chartc", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def clamp(value: float, low: int, high: int) -> int:
    return max(low, min(high, round(value)))


def bool_mask(values, count: int) -> int:
    mask = 0
    for index, value in enumerate(list(values or [])[:count]):
        if value:
            mask |= 1 << index
    return mask


def parse_color(value) -> int:
    text = str(value or "0").strip().lower().replace("#", "")
    if text.startswith("0x"):
        text = text[2:]
    if len(text) == 8:
        text = text[2:]
    try:
        return int(text[-6:], 16)
    except ValueError:
        return 0


def event_row(event: dict, changes, chartc) -> tuple[int, ...] | None:
    name = event.get("e")
    if name not in EVENT_KIND:
        return None
    value = event.get("v") or {}
    step = chartc.round_half_up(chartc.time_to_beat(float(event.get("t", 0)), changes) * 4.0)
    kind = EVENT_KIND[name]
    flags = 0
    a = b = c = d = 0
    color0 = color1 = 0

    if name == "FocusCamera":
        # All SPAGHETTI focus events are explicit stage-space positions.
        a = round((float(value.get("x", 620)) - 620.0) * 0.22)
        b = round((float(value.get("y", 400)) - 400.0) * 0.22)
        c = clamp(float(value.get("duration", 0)) * 4.0, 0, 32767)
    elif name == "ZoomCamera":
        a = clamp(float(value.get("zoom", 1.0)) * 1024.0, 1, 32767)
        b = clamp(float(value.get("duration", 0)) * 4.0, 0, 32767)
    elif name == "SetCameraBop":
        a = clamp(float(value.get("rate", 4)), 0, 32767)
        b = clamp(float(value.get("intensity", 0)) * 100.0, 0, 32767)
        c = clamp(float(value.get("offset", 0)), -32768, 32767)
    elif name == "sserafimShow":
        flags = bool_mask(value.get("visible"), 5)
    elif name == "sserafimSing":
        flags = bool_mask(value.get("singing"), 6)
    elif name == "sserafimDark":
        a = clamp(float(value.get("amount", 0)) * 255.0, 0, 255)
        b = clamp(float(value.get("duration", 0)) * 1000.0, 0, 32767)
    elif name == "sserafimLights":
        a = clamp(float(value.get("amount", 0)) * 255.0, 0, 255)
        b = clamp(float(value.get("duration", 0)) * 1000.0, 0, 32767)
    elif name == "sserafimCover":
        flags = 1 if value.get("visible") else 0
    elif name == "sserafimFlash":
        b = clamp(float(value.get("duration", 0)) * 1000.0, 0, 32767)
    elif name == "sserafimPulseLights":
        flags = 1 if value.get("enabled") else 0
        colors = list(value.get("colors") or [])
        durations = list(value.get("durations") or [])
        intensities = list(value.get("intensities") or [])
        color0 = parse_color(colors[0]) if colors else 0
        color1 = parse_color(colors[1] if len(colors) > 1 else (colors[0] if colors else 0))
        a = clamp(float(intensities[0] if intensities else 0) * 255.0, 0, 255)
        b = clamp(float(durations[0] if durations else 0.5) * 1000.0, 0, 32767)
        c = clamp(float(intensities[1] if len(intensities) > 1 else (intensities[0] if intensities else 0)) * 255.0, 0, 255)
        d = clamp(float(durations[1] if len(durations) > 1 else (durations[0] if durations else 0.5)) * 1000.0, 0, 32767)
    elif name == "sserafimKick":
        flags = 1 if value.get("final") else 0
    elif name == "sserafimBeautiful":
        flags = 1 if value.get("beautiful") else 0
    elif name == "sserafimGuitarVibration":
        b = clamp(float(value.get("duration", 0)) * 1000.0, 0, 32767)
    elif name == "SetHealthIcon":
        flags = clamp(float(value.get("char", 1)), 0, 1)
        a = ICON_IDS.get(str(value.get("id", "bf")).lower(), 0)

    return step, kind, flags, a, b, c, d, color0, color1


def write_header(path: Path, rows: list[tuple[int, ...]]) -> None:
    lines = [
        "#ifndef _SSERAFIM_EVENTS_GENERATED_H",
        "#define _SSERAFIM_EVENTS_GENERATED_H",
        "",
        "static const SserafimEvent sserafim_events[] = {",
    ]
    for row in rows:
        step, kind, flags, a, b, c, d, color0, color1 = row
        lines.append(
            f"    {{{step}, {kind}, {flags}, {a}, {b}, {c}, {d}, 0x{color0:06X}, 0x{color1:06X}}},"
        )
    lines.extend([
        "};",
        f"#define SSERAFIM_EVENT_COUNT {len(rows)}",
        "#endif",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--iso-root", type=Path, required=True)
    parser.add_argument("--header", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    chartc = load_chartc()
    song_dir = args.root / "data/songs/spaghetti"
    chart = json.loads((song_dir / "spaghetti-chart.json").read_text())
    metadata = json.loads((song_dir / "spaghetti-metadata.json").read_text())
    # The official final non-scoreable note exists only to keep script timing alive.
    clean_chart = json.loads(json.dumps(chart))
    for notes in clean_chart.get("notes", {}).values():
        notes[:] = [note for note in notes if note.get("k") != "non_scoreable"]

    out = args.iso_root / "chart"
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for difficulty, suffix in (("easy", "e"), ("normal", "n"), ("hard", "h")):
        payload = chartc.convert(clean_chart, metadata, difficulty, kind_codes=KIND_CODES)
        target = out / f"9.1{suffix}.cht"
        target.write_bytes(payload)
        records.append({"difficulty": difficulty, "file": target.name, "bytes": len(payload)})

    changes = chartc.read_time_changes(metadata)
    rows = [row for event in chart.get("events", []) if (row := event_row(event, changes, chartc)) is not None]
    rows.sort(key=lambda row: row[0])
    write_header(args.header, rows)

    counts = {}
    for event in chart.get("events", []):
        if event.get("e") in EVENT_KIND:
            counts[event["e"]] = counts.get(event["e"], 0) + 1
    report = {
        "policy": "official-v0.8.4-spaghetti-chart-and-events",
        "charts": records,
        "event_count": len(rows),
        "event_counts": counts,
        "note_kind_codes": KIND_CODES,
        "removed_non_scoreable_tail_note": True,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
