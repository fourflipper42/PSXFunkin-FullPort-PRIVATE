#!/usr/bin/env python3
"""Convert Better Alphabet 2.x font data and atlases into PS2 runtime assets."""

from __future__ import annotations

import argparse
import importlib.util
import json
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MAGIC = b"FBAL"
VERSION = 1
HEADER = struct.Struct("<4sHHIIIIiiiiiiiiI")
BLOCK = struct.Struct("<I")
GLYPH = struct.Struct("<IhhHHHH")
NO_FRAME = 0xFFFF
FLAG_ANTIALIAS = 1 << 0
GLYPH_MONO_OVERRIDE = 1 << 0
GLYPH_MONO_VALUE = 1 << 1


def load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def parse_bool(value: str) -> bool:
    return value.strip().lower() in ("true", "1", "yes", "on")


def parse_map(path: Path) -> dict[int, dict]:
    result: dict[int, dict] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        values: dict[str, str] = {}
        for item in line.split():
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            values[key] = value
        if "char" not in values:
            continue
        codepoint = int(values["char"], 0)
        entry = {
            "offsetX": int(values.get("offsetX", "0")),
            "offsetY": int(values.get("offsetY", "0")),
            "monoOverride": "monospace" in values,
            "monospace": parse_bool(values.get("monospace", "false")),
        }
        result[codepoint] = entry
    return result


def xml_codepoint_frames(xml_path: Path) -> dict[int, int]:
    root = ET.parse(xml_path).getroot()
    result: dict[int, int] = {}
    for index, node in enumerate(root.findall(".//SubTexture")):
        name = node.get("name") or ""
        prefix = name.split("-", 1)[0]
        try:
            codepoint = int(prefix, 10)
        except ValueError:
            continue
        result.setdefault(codepoint, index)
    return result


def add_string(strings: bytearray, cache: dict[str, int], value: str) -> int:
    if value in cache:
        return cache[value]
    off = len(strings)
    strings.extend(value.encode("utf-8") + b"\0")
    cache[value] = off
    return off


def convert(mod_root: Path, output_root: Path) -> dict:
    atlas_converter = load_module("convert_sparrow_atlas.py", "convert_sparrow_balphabet")
    mod_root = mod_root.resolve()
    data_root = mod_root / "data" / "balphabet" / "default"
    image_root = mod_root / "images" / "balphabet" / "default"
    if not data_root.is_dir() or not image_root.is_dir():
        raise FileNotFoundError("Better Alphabet default font folders not found")

    config = json.loads((data_root / "default.json").read_text(encoding="utf-8"))
    block_files = sorted(path for path in data_root.glob("*.txt") if path.is_file())
    strings = bytearray()
    cache: dict[str, int] = {}
    block_blob = bytearray()
    glyphs: dict[int, dict] = {}
    converted_blocks: list[dict] = []

    for block_index, map_path in enumerate(block_files):
        block_name = map_path.stem
        block_blob.extend(BLOCK.pack(add_string(strings, cache, block_name)))
        mapping = parse_map(map_path)
        frames_by_style: dict[str, dict[int, int]] = {}

        for style in ("regular", "bold"):
            png = image_root / style / f"{block_name}.png"
            xml = image_root / style / f"{block_name}.xml"
            if not png.exists() or not xml.exists():
                frames_by_style[style] = {}
                continue
            out_stem = output_root / style.upper() / block_name.upper() / "GLYPH"
            frame_count, page_count = atlas_converter.convert(png, xml, out_stem)
            frames_by_style[style] = xml_codepoint_frames(xml)
            converted_blocks.append({
                "block": block_name,
                "style": style,
                "frames": frame_count,
                "pages": page_count,
            })

        for codepoint, info in mapping.items():
            flags = 0
            if info["monoOverride"]:
                flags |= GLYPH_MONO_OVERRIDE
            if info["monospace"]:
                flags |= GLYPH_MONO_VALUE
            glyphs[codepoint] = {
                "codepoint": codepoint,
                "offsetX": info["offsetX"],
                "offsetY": info["offsetY"],
                "block": block_index,
                "regular": frames_by_style["regular"].get(codepoint, NO_FRAME),
                "bold": frames_by_style["bold"].get(codepoint, NO_FRAME),
                "flags": flags,
            }

    glyph_blob = bytearray()
    for codepoint in sorted(glyphs):
        item = glyphs[codepoint]
        if item["regular"] == NO_FRAME and item["bold"] == NO_FRAME:
            continue
        glyph_blob.extend(GLYPH.pack(
            item["codepoint"],
            item["offsetX"],
            item["offsetY"],
            item["block"],
            item["regular"],
            item["bold"],
            item["flags"],
        ))

    flags = FLAG_ANTIALIAS if bool(config.get("antialiasing", True)) else 0
    header = HEADER.pack(
        MAGIC,
        VERSION,
        len(block_files),
        len(glyph_blob) // GLYPH.size,
        len(strings),
        BLOCK.size,
        GLYPH.size,
        int(config.get("height", 54)),
        int(config.get("heightBold", config.get("height", 54))),
        int(config.get("width", 54)),
        int(config.get("widthBold", config.get("width", 54))),
        int(config.get("padding", 2)),
        int(config.get("paddingBold", config.get("padding", 2))),
        int(config.get("lineHeight", 85)),
        int(config.get("spaceWidth", 28)),
        flags,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    catalog = output_root / "FONT.FBAL"
    catalog.write_bytes(header + block_blob + glyph_blob + strings)

    result = {
        "glyphs": len(glyph_blob) // GLYPH.size,
        "blocks": [path.stem for path in block_files],
        "atlases": converted_blocks,
        "metrics": config,
        "binary": catalog.as_posix(),
        "binaryBytes": catalog.stat().st_size,
    }
    (output_root / "FONT.JSON").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mod_root", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    convert(args.mod_root, args.output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
