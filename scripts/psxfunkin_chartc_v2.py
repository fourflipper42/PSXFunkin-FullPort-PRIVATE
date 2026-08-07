#!/usr/bin/env python3
"""Convert modern FNF v2 chart/metadata JSON into PSXFunkin .CHT files.

PSXFunkin chart format (little-endian):
  u16 notes_offset
  Section sections[]: u16 end_pos, u16 flags
  Note notes[]: u16 pos, u8 type, u8 pad

Positions are 1/12 of an FNF step (48 units per beat).
"""
from __future__ import annotations
import argparse
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SECTION_FLAG_OPPFOCUS = 1 << 15
SECTION_FLAG_BPM_MASK = 0x7FFF
NOTE_FLAG_OPPONENT = 1 << 2
NOTE_FLAG_SUSTAIN = 1 << 3
NOTE_FLAG_SUSTAIN_END = 1 << 4
NOTE_FLAG_ALT_ANIM = 1 << 5
NOTE_FLAG_MINE = 1 << 6
NOTE_FLAG_HIT = 1 << 7
UNITS_PER_STEP = 12
UNITS_PER_BEAT = 48
UNITS_PER_SECTION = 16 * UNITS_PER_STEP

@dataclass(frozen=True)
class TimeChange:
    time_ms: float
    beat: float
    bpm: float


def round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def read_time_changes(metadata: dict[str, Any]) -> list[TimeChange]:
    changes: list[TimeChange] = []
    for item in metadata.get("timeChanges", []):
        changes.append(TimeChange(float(item.get("t", 0)), float(item.get("b", 0)), float(item["bpm"])))
    if not changes:
        raise ValueError("metadata has no timeChanges")
    changes.sort(key=lambda x: x.time_ms)
    return changes


def time_to_beat(time_ms: float, changes: list[TimeChange]) -> float:
    active = changes[0]
    for change in changes[1:]:
        if change.time_ms > time_ms:
            break
        active = change
    return active.beat + (time_ms - active.time_ms) * active.bpm / 60000.0


def bpm_at_beat(beat: float, changes: list[TimeChange]) -> float:
    active = changes[0]
    for change in changes[1:]:
        if change.beat > beat:
            break
        active = change
    return active.bpm


def normalize_focus_value(value: Any) -> int | None:
    if isinstance(value, dict):
        value = value.get("char")
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"player", "boyfriend", "bf", "0"}:
            return 0
        if low in {"opponent", "dad", "1"}:
            return 1
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def focus_events(chart: dict[str, Any], changes: list[TimeChange]) -> list[tuple[float, int]]:
    result: list[tuple[float, int]] = []
    for event in chart.get("events", []):
        if event.get("e") != "FocusCamera":
            continue
        focus = normalize_focus_value(event.get("v"))
        if focus not in (0, 1):
            continue
        result.append((time_to_beat(float(event.get("t", 0)), changes), focus))
    result.sort(key=lambda x: x[0])
    return result


def focus_at_beat(beat: float, events: list[tuple[float, int]]) -> int:
    focus = 0
    for event_beat, event_focus in events:
        if event_beat > beat + 1e-9:
            break
        focus = event_focus
    return focus


def convert(chart: dict[str, Any], metadata: dict[str, Any], difficulty: str,
            section_count: int | None = None, kind_codes: dict[str, int] | None = None) -> bytes:
    changes = read_time_changes(metadata)
    source_notes = chart["notes"][difficulty]
    notes: list[tuple[int, int, int]] = []
    max_beat = 0.0

    for item in source_notes:
        time_ms = float(item["t"])
        direction = int(item["d"])
        if direction < 0:
            raise ValueError(f"invalid direction {direction}")
        pos = round_half_up(time_to_beat(time_ms, changes) * UNITS_PER_BEAT)
        note_type = direction & 0x07
        kind = str(item.get("k", "")).lower()
        pad = 0 if kind_codes is None else kind_codes.get(kind, 0)
        if "mine" in kind:
            note_type |= NOTE_FLAG_MINE
        if item.get("alt") is True or "alt" in kind:
            note_type |= NOTE_FLAG_ALT_ANIM

        sustain_ms = max(0.0, float(item.get("l", 0)))
        sustain_steps = 0
        if sustain_ms > 0:
            start_beat = time_to_beat(time_ms, changes)
            end_beat = time_to_beat(time_ms + sustain_ms, changes)
            sustain_steps = max(0, round_half_up((end_beat - start_beat) * 4.0) - 1)
            note_type |= NOTE_FLAG_SUSTAIN_END

        notes.append((pos, note_type, pad))
        for index in range(sustain_steps + (1 if sustain_ms > 0 else 0)):
            sustain_type = note_type | NOTE_FLAG_SUSTAIN
            if index != sustain_steps:
                sustain_type &= ~NOTE_FLAG_SUSTAIN_END
            notes.append((pos + (index + 1) * UNITS_PER_STEP, sustain_type, pad))

        max_beat = max(max_beat, time_to_beat(time_ms + sustain_ms, changes))

    # Match PSXFunkin ordering: heads before sustains at the same position.
    notes.sort(key=lambda n: (n[0], 1 if (n[1] & NOTE_FLAG_SUSTAIN) else 0))

    events = focus_events(chart, changes)
    if events:
        max_beat = max(max_beat, events[-1][0])
    if section_count is None:
        section_count = max(1, math.ceil(max_beat / 4.0))

    sections: list[tuple[int, int]] = []
    for index in range(section_count):
        start_beat = index * 4.0
        end_pos = (index + 1) * UNITS_PER_SECTION
        bpm_flag = round_half_up(bpm_at_beat(start_beat, changes) * 24.0) & SECTION_FLAG_BPM_MASK
        if focus_at_beat(start_beat, events) == 1:
            bpm_flag |= SECTION_FLAG_OPPFOCUS
        sections.append((end_pos, bpm_flag))

    # Sentinels expected by PSXFunkin's pointer-walking runtime.
    last_flag = sections[-1][1]
    sections.append((0xFFFF, last_flag))
    notes.append((0xFFFF, NOTE_FLAG_HIT, 0))

    notes_offset = 2 + len(sections) * 4
    out = bytearray(struct.pack("<H", notes_offset))
    for end_pos, flags in sections:
        out += struct.pack("<HH", end_pos, flags)
    for pos, note_type, pad in notes:
        if not 0 <= pos <= 0xFFFF:
            raise ValueError(f"note position out of range: {pos}")
        out += struct.pack("<HBB", pos, note_type, pad)
    return bytes(out)


def decode_section_count(path: Path) -> int:
    data = path.read_bytes()
    notes_offset = struct.unpack_from("<H", data, 0)[0]
    total_sections = (notes_offset - 2) // 4
    if total_sections < 2:
        raise ValueError(f"invalid template chart: {path}")
    return total_sections - 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chart", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--difficulty", choices=("easy", "normal", "hard", "erect", "nightmare"), required=True)
    parser.add_argument("--template", type=Path, help="Legacy CHT used only to preserve section count")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    chart = json.loads(args.chart.read_text())
    metadata = json.loads(args.metadata.read_text())
    section_count = decode_section_count(args.template) if args.template else None
    result = convert(chart, metadata, args.difficulty, section_count)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result)
    print(f"{args.output}: {len(result)} bytes")

if __name__ == "__main__":
    main()
