#!/usr/bin/env python3
"""Convert modern FNF note styles into PS2 runtime assets."""

from __future__ import annotations

import argparse
import importlib.util
import json
import struct
import sys
from pathlib import Path

from note_style_assets import find_asset, find_note_style_json

MAGIC = b"FNST"
VERSION = 1
FLAG_NOTE_PIXEL = 1 << 0
FLAG_STRUM_PIXEL = 1 << 1
FLAG_HOLD_PIXEL = 1 << 2
HEADER = struct.Struct("<4sHH7fI20I")
DIRECTIONS = ("left", "down", "up", "right")


def load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def pair(value) -> tuple[float, float]:
    if isinstance(value, list) and len(value) >= 2:
        return float(value[0]), float(value[1])
    return 0.0, 0.0


def style_scale(asset: dict) -> float:
    return float(asset.get("scale", 1.0) or 1.0) * 0.5


def prefix(asset: dict, key: str) -> str:
    entry = (asset.get("data") or {}).get(key) or {}
    value = entry.get("prefix") if isinstance(entry, dict) else None
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing prefix for {key}")
    return value


def add_string(strings: bytearray, cache: dict[str, int], value: str) -> int:
    if value in cache:
        return cache[value]
    offset = len(strings)
    strings.extend(value.encode("utf-8") + b"\0")
    cache[value] = offset
    return offset


def convert(assets_root: Path, style_id: str, output_dir: Path) -> dict:
    atlas = load_module("convert_sparrow_atlas.py", "convert_sparrow_atlas")
    texture = load_module("convert_texture.py", "convert_texture")
    style_path = find_note_style_json(assets_root, style_id)
    style = json.loads(style_path.read_text(encoding="utf-8"))
    assets = style.get("assets") or {}
    note = assets.get("note") or {}
    strum = assets.get("noteStrumline") or {}
    hold = assets.get("holdNote") or {}

    note_path = str(note.get("assetPath") or "")
    strum_path = str(strum.get("assetPath") or "")
    hold_path = str(hold.get("assetPath") or "")
    if not note_path or not strum_path or not hold_path:
        raise ValueError(f"{style_id}: incomplete gameplay note assets")

    output_dir.mkdir(parents=True, exist_ok=True)
    note_frames, note_pages = atlas.convert(
        find_asset(assets_root, note_path, ".png"),
        find_asset(assets_root, note_path, ".xml"),
        output_dir / "NOTE",
    )
    strum_frames, strum_pages = atlas.convert(
        find_asset(assets_root, strum_path, ".png"),
        find_asset(assets_root, strum_path, ".xml"),
        output_dir / "STRUM",
    )
    hold_w, hold_h = texture.convert(
        find_asset(assets_root, hold_path, ".png"),
        output_dir / "HOLD.FPTX",
    )
    if hold_w % 8 != 0:
        raise ValueError(f"{style_id}: hold texture width {hold_w} is not divisible by 8")

    strings = bytearray()
    cache: dict[str, int] = {}
    groups = [
        [prefix(note, d) for d in DIRECTIONS],
        [prefix(strum, f"{d}Static") for d in DIRECTIONS],
        [prefix(strum, f"{d}Press") for d in DIRECTIONS],
        [prefix(strum, f"{d}Confirm") for d in DIRECTIONS],
        [prefix(strum, f"{d}ConfirmHold") for d in DIRECTIONS],
    ]
    offsets = [add_string(strings, cache, value) for group in groups for value in group]
    strum_x, strum_y = pair(strum.get("offsets"))
    hold_x, hold_y = pair(hold.get("offsets"))
    flags = 0
    if note.get("isPixel"):
        flags |= FLAG_NOTE_PIXEL
    if strum.get("isPixel"):
        flags |= FLAG_STRUM_PIXEL
    if hold.get("isPixel"):
        flags |= FLAG_HOLD_PIXEL

    payload = HEADER.pack(
        MAGIC, VERSION, flags,
        style_scale(note), style_scale(strum), style_scale(hold),
        strum_x * 0.5, strum_y * 0.5,
        hold_x * 0.5, hold_y * 0.5,
        len(strings), *offsets,
    ) + strings
    (output_dir / "STYLE.FNST").write_bytes(payload)

    result = {
        "id": style_id,
        "source": style_path.as_posix(),
        "noteFrames": note_frames,
        "notePages": note_pages,
        "strumFrames": strum_frames,
        "strumPages": strum_pages,
        "holdSize": [hold_w, hold_h],
        "pixel": bool(flags),
    }
    print(json.dumps(result, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("assets_root", type=Path)
    parser.add_argument("style_id")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    convert(args.assets_root.resolve(), args.style_id, args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
