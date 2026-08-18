#!/usr/bin/env python3
"""Convert modern FNF chart events into a compact lossless PS2 sidecar.

Every event keeps its original name and JSON value so adding a new runtime
handler never requires changing the on-disc format or reconverting charts.
Frequently-used events may also receive normalized numeric arguments for cheap
PS2-side dispatch.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Any

MAGIC = b"FEVT"
VERSION = 1
NO_STRING = 0xFFFFFFFF

HEADER = struct.Struct("<4sHHIIII")
RECORD = struct.Struct("<iHHffII")

EVENT_GENERIC = 0
EVENT_FOCUS_CAMERA = 1


def add_string(strings: bytearray, cache: dict[str, int], value: str) -> int:
    if value in cache:
        return cache[value]
    offset = len(strings)
    strings.extend(value.encode("utf-8") + b"\0")
    cache[value] = offset
    return offset


def normalize_focus(value: Any) -> int | None:
    if isinstance(value, dict):
        value = value.get("char")
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"player", "boyfriend", "bf", "0"}:
            return 0
        if low in {"opponent", "dad", "1"}:
            return 1
        if low in {"girlfriend", "gf", "2"}:
            return 2
        return None
    if isinstance(value, (int, float)):
        ivalue = int(value)
        return ivalue if ivalue in (0, 1, 2) else None
    return None


def encode_events(chart: dict[str, Any]) -> tuple[bytes, int]:
    source = chart.get("events") or []
    if not isinstance(source, list):
        raise ValueError("chart events must be an array")
    if len(source) > 0xFFFFFFFF:
        raise ValueError("too many chart events")

    strings = bytearray()
    cache: dict[str, int] = {}
    encoded: list[tuple[int, int, int, float, float, int, int, int]] = []

    for source_index, event in enumerate(source):
        if not isinstance(event, dict):
            raise ValueError(f"event {source_index} is not an object")

        name = str(event.get("e") or "")
        if not name:
            raise ValueError(f"event {source_index} has no event name")
        try:
            time_us = int(round(float(event.get("t", 0.0)) * 1000.0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"event {source_index}/{name}: invalid time") from exc
        if not -0x80000000 <= time_us <= 0x7FFFFFFF:
            raise ValueError(f"event {source_index}/{name}: time outside s32 microseconds")

        value = event.get("v")
        value_json = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        name_off = add_string(strings, cache, name)
        value_off = add_string(strings, cache, value_json)

        kind = EVENT_GENERIC
        flags = 0
        arg0 = 0.0
        arg1 = 0.0
        if name == "FocusCamera":
            focus = normalize_focus(value)
            if focus is not None:
                kind = EVENT_FOCUS_CAMERA
                arg0 = float(focus)

        encoded.append((time_us, kind, flags, arg0, arg1, name_off, value_off, source_index))

    # Preserve source order for simultaneous events while making timing monotonic.
    encoded.sort(key=lambda row: (row[0], row[7]))
    records = bytearray()
    for time_us, kind, flags, arg0, arg1, name_off, value_off, _ in encoded:
        records.extend(RECORD.pack(time_us, kind, flags, arg0, arg1, name_off, value_off))

    header = HEADER.pack(
        MAGIC,
        VERSION,
        0,
        len(encoded),
        RECORD.size,
        len(strings),
        0,
    )
    return bytes(header + records + strings), len(encoded)


def convert(chart_path: Path, output_path: Path) -> int:
    chart = json.loads(chart_path.read_text(encoding="utf-8"))
    payload, count = encode_events(chart)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    print(f"{chart_path} -> {output_path}: {count} event(s), {len(payload):,} bytes")
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("chart", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    convert(args.chart, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
