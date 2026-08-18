#!/usr/bin/env python3
"""Convert a Sparrow PNG+XML atlas into PS2 texture + frame table files."""

from __future__ import annotations

import argparse
import importlib.util
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HEADER = struct.Struct("<4sHHII")
RECORD = struct.Struct("<IHHHHhhHHHH")
MAGIC = b"FATL"
VERSION = 1


def load_texture_converter():
    path = Path(__file__).with_name("convert_texture.py")
    spec = importlib.util.spec_from_file_location("convert_texture", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def as_int(node: ET.Element, key: str, default: int = 0) -> int:
    value = node.get(key)
    return default if value is None or value == "" else int(value)


def checked_u16(value: int, label: str) -> int:
    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"{label} out of range: {value}")
    return value


def checked_s16(value: int, label: str) -> int:
    if not -0x8000 <= value <= 0x7FFF:
        raise ValueError(f"{label} out of range: {value}")
    return value


def convert_frames(xml_path: Path, output_path: Path) -> int:
    root = ET.parse(xml_path).getroot()
    frames = list(root.findall(".//SubTexture"))
    if not frames:
        raise ValueError(f"no SubTexture entries in {xml_path}")
    if len(frames) > 0xFFFF:
        raise ValueError(f"too many frames: {len(frames)}")

    strings = bytearray()
    records = bytearray()

    for frame in frames:
        name = frame.get("name")
        if not name:
            raise ValueError("SubTexture is missing name")
        encoded = name.encode("utf-8") + b"\0"
        name_offset = len(strings)
        strings.extend(encoded)

        x = checked_u16(as_int(frame, "x"), "x")
        y = checked_u16(as_int(frame, "y"), "y")
        w = checked_u16(as_int(frame, "width"), "width")
        h = checked_u16(as_int(frame, "height"), "height")
        frame_x = checked_s16(as_int(frame, "frameX", 0), "frameX")
        frame_y = checked_s16(as_int(frame, "frameY", 0), "frameY")
        frame_w = checked_u16(as_int(frame, "frameWidth", w), "frameWidth")
        frame_h = checked_u16(as_int(frame, "frameHeight", h), "frameHeight")
        rotated = 1 if str(frame.get("rotated", "false")).lower() in ("true", "1") else 0

        records.extend(
            RECORD.pack(
                name_offset,
                x,
                y,
                w,
                h,
                frame_x,
                frame_y,
                frame_w,
                frame_h,
                rotated,
                0,
            )
        )

    header = HEADER.pack(MAGIC, VERSION, len(frames), len(strings), RECORD.size)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(header + records + strings)
    return len(frames)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("png", type=Path)
    parser.add_argument("xml", type=Path)
    parser.add_argument("output_stem", type=Path, help="Output path without extension")
    args = parser.parse_args()

    texture_converter = load_texture_converter()
    texture_path = args.output_stem.with_suffix(".FPTX")
    frames_path = args.output_stem.with_suffix(".FATL")
    texture_converter.convert(args.png, texture_path)
    count = convert_frames(args.xml, frames_path)
    print(f"{args.xml} -> {frames_path}: {count} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
