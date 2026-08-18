#!/usr/bin/env python3
"""Convert Pointless Pins JSON data into a compact PS2 runtime catalog."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

MAGIC = b"FPIN"
VERSION = 1
NO_STRING = 0xFFFFFFFF

HEADER = struct.Struct("<4sHHHHIIIIII")
RARITY = struct.Struct("<IIHH")
PIN = struct.Struct("<IIIIfHH")
BOX = struct.Struct("<IIIHHHHI")
CHANCE = struct.Struct("<HH")

PIN_SPECIAL = 1 << 0
BOX_SPECIAL = 1 << 0


def add_string(strings: bytearray, cache: dict[str, int], value: object) -> int:
    if value is None:
        return NO_STRING
    text = str(value)
    if text in cache:
        return cache[text]
    off = len(strings)
    strings.extend(text.encode("utf-8") + b"\0")
    cache[text] = off
    return off


def color_rgba(value: object) -> int:
    text = str(value or "FFFFFF").strip().lstrip("#")
    if len(text) == 6:
        text += "FF"
    if len(text) != 8:
        return 0xFFFFFFFF
    try:
        r = int(text[0:2], 16)
        g = int(text[2:4], 16)
        b = int(text[4:6], 16)
        a = int(text[6:8], 16)
    except ValueError:
        return 0xFFFFFFFF
    return r | (g << 8) | (b << 16) | (a << 24)


def convert(pins_json: Path, boxes_json: Path, output: Path, manifest: Path | None) -> dict:
    pins_data = json.loads(pins_json.read_text(encoding="utf-8"))
    boxes_data = json.loads(boxes_json.read_text(encoding="utf-8"))

    strings = bytearray()
    cache: dict[str, int] = {}
    rarity_blob = bytearray()
    pin_blob = bytearray()
    box_blob = bytearray()
    chance_blob = bytearray()
    rarity_names = sorted(
        pins_data.keys(),
        key=lambda name: (int(pins_data[name].get("order", 0)), name.lower()),
    )
    rarity_index = {name: i for i, name in enumerate(rarity_names)}
    manifest_pins: list[dict] = []
    first_pin = 0

    for rarity_name in rarity_names:
        rarity = pins_data[rarity_name]
        pins = rarity.get("pins") or []
        rarity_blob.extend(
            RARITY.pack(
                add_string(strings, cache, rarity_name),
                color_rgba(rarity.get("color")),
                first_pin,
                len(pins),
            )
        )
        for pin in pins:
            flags = PIN_SPECIAL if bool(pin.get("special", False)) else 0
            pin_blob.extend(
                PIN.pack(
                    add_string(strings, cache, pin.get("id", "")),
                    add_string(strings, cache, pin.get("name", "")),
                    add_string(strings, cache, pin.get("description")),
                    add_string(strings, cache, pin.get("lockedText")),
                    float(pin.get("scale", 0.5)),
                    rarity_index[rarity_name],
                    flags,
                )
            )
            manifest_pins.append({
                "id": pin.get("id", ""),
                "name": pin.get("name", ""),
                "rarity": rarity_name,
                "special": bool(flags & PIN_SPECIAL),
            })
        first_pin += len(pins)

    manifest_boxes: list[dict] = []
    for box in sorted(boxes_data, key=lambda item: (float(item.get("order", 0)), str(item.get("id", "")))):
        start = len(chance_blob) // CHANCE.size
        chances = box.get("chances") or []
        for chance in chances:
            if not isinstance(chance, list) or len(chance) < 2:
                raise ValueError(f"bad box chance: {chance!r}")
            rarity_name = str(chance[0])
            if rarity_name not in rarity_index:
                raise ValueError(f"unknown rarity {rarity_name!r}")
            weight = int(chance[1])
            if not 0 <= weight <= 0xFFFF:
                raise ValueError(f"weight out of range: {weight}")
            chance_blob.extend(CHANCE.pack(rarity_index[rarity_name], weight))
        flags = BOX_SPECIAL if bool(box.get("special", False)) else 0
        box_blob.extend(
            BOX.pack(
                add_string(strings, cache, box.get("id", "")),
                add_string(strings, cache, box.get("name", "")),
                add_string(strings, cache, box.get("description", "")),
                int(box.get("cost", 0)),
                int(box.get("revealTime", 26)),
                start,
                len(chances),
                flags,
            )
        )
        manifest_boxes.append({
            "id": box.get("id", ""),
            "cost": int(box.get("cost", 0)),
            "chances": chances,
        })

    pin_count = len(pin_blob) // PIN.size
    box_count = len(box_blob) // BOX.size
    chance_count = len(chance_blob) // CHANCE.size
    if pin_count > 64:
        raise ValueError(f"PS2 save currently supports 64 pins, got {pin_count}")
    if box_count > 8:
        raise ValueError(f"PS2 save currently supports 8 boxes, got {box_count}")

    header = HEADER.pack(
        MAGIC,
        VERSION,
        len(rarity_names),
        pin_count,
        box_count,
        RARITY.size,
        PIN.size,
        BOX.size,
        CHANCE.size,
        chance_count,
        len(strings),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(header + rarity_blob + pin_blob + box_blob + chance_blob + strings)

    result = {
        "rarities": rarity_names,
        "pinCount": pin_count,
        "boxCount": box_count,
        "chanceCount": chance_count,
        "pins": manifest_pins,
        "boxes": manifest_boxes,
        "binaryBytes": output.stat().st_size,
    }
    if manifest is not None:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pins_json", type=Path)
    parser.add_argument("boxes_json", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()
    convert(args.pins_json, args.boxes_json, args.output, args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
