#!/usr/bin/env python3
"""Convert FNF LevelData JSON files into a compact PS2 Story Mode catalog."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

MAGIC = b"FSTY"
VERSION = 1
HEADER = struct.Struct("<4sHHIIII")
LEVEL = struct.Struct("<IIIIHHII")
NO_STRING = 0xFFFFFFFF

BASE_ORDER = [
    "tutorial",
    "week1",
    "week2",
    "week3",
    "week4",
    "week5",
    "week6",
    "week7",
    "weekend1",
    "sserafim",
]

FLAG_VISIBLE = 1 << 0


def find_levels_root(assets_root: Path) -> Path:
    direct = assets_root / "data" / "levels"
    if direct.is_dir():
        return direct
    for candidate in assets_root.rglob("levels"):
        if candidate.is_dir() and candidate.parent.name == "data":
            return candidate
    raise FileNotFoundError(f"data/levels not found under {assets_root}")


def add_string(strings: bytearray, cache: dict[str, int], value: str) -> int:
    if value in cache:
        return cache[value]
    offset = len(strings)
    strings.extend(value.encode("utf-8") + b"\0")
    cache[value] = offset
    return offset


def parse_color(value: object) -> int:
    text = str(value or "#F9CF51").strip().lstrip("#")
    if len(text) == 6:
        text += "FF"
    if len(text) != 8:
        return 0xFFF9CF51
    try:
        r = int(text[0:2], 16)
        g = int(text[2:4], 16)
        b = int(text[4:6], 16)
        a = int(text[6:8], 16)
    except ValueError:
        return 0xFFF9CF51
    return r | (g << 8) | (b << 16) | (a << 24)


def ordered_ids(found: set[str]) -> list[str]:
    result = [level_id for level_id in BASE_ORDER if level_id in found]
    result.extend(sorted(found.difference(result)))
    return result


def convert(assets_root: Path, output: Path, manifest_path: Path | None = None) -> dict:
    levels_root = find_levels_root(assets_root.resolve())
    files: dict[str, Path] = {
        path.stem: path for path in levels_root.glob("*.json") if path.is_file()
    }

    strings = bytearray()
    cache: dict[str, int] = {}
    records = bytearray()
    song_offsets: list[int] = []
    manifest_levels: list[dict] = []

    for level_id in ordered_ids(set(files)):
        path = files[level_id]
        data = json.loads(path.read_text(encoding="utf-8"))
        name = str(data.get("name") or level_id)
        title_asset = str(data.get("titleAsset") or "")
        songs = data.get("songs") or []
        if not isinstance(songs, list) or not songs:
            raise ValueError(f"{path}: Story level has no songs")
        song_ids = [str(song) for song in songs if str(song)]
        if not song_ids:
            raise ValueError(f"{path}: Story level has no valid song IDs")

        id_off = add_string(strings, cache, level_id)
        name_off = add_string(strings, cache, name)
        title_off = add_string(strings, cache, title_asset)
        song_start = len(song_offsets)
        for song_id in song_ids:
            song_offsets.append(add_string(strings, cache, song_id))

        flags = FLAG_VISIBLE if bool(data.get("visible", True)) else 0
        background = parse_color(data.get("background"))
        records.extend(
            LEVEL.pack(
                id_off,
                name_off,
                title_off,
                song_start,
                len(song_ids),
                flags,
                background,
                0,
            )
        )
        manifest_levels.append(
            {
                "id": level_id,
                "name": name,
                "titleAsset": title_asset,
                "visible": bool(flags & FLAG_VISIBLE),
                "background": data.get("background", "#F9CF51"),
                "songs": song_ids,
                "source": path.as_posix(),
            }
        )

    if len(manifest_levels) > 0xFFFF:
        raise ValueError("too many Story Mode levels")
    if len(song_offsets) > 0xFFFFFFFF:
        raise ValueError("too many Story Mode song references")

    songs_blob = struct.pack(f"<{len(song_offsets)}I", *song_offsets) if song_offsets else b""
    header = HEADER.pack(
        MAGIC,
        VERSION,
        len(manifest_levels),
        LEVEL.size,
        len(song_offsets),
        len(strings),
        0,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(header + records + songs_blob + strings)

    manifest = {
        "format": "FNF PS2 Story Catalog",
        "sourceRoot": levels_root.as_posix(),
        "levels": manifest_levels,
        "levelCount": len(manifest_levels),
        "songReferences": len(song_offsets),
        "binary": output.as_posix(),
        "binaryBytes": output.stat().st_size,
    }
    if manifest_path is not None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Story levels: {len(manifest_levels)}")
    print(f"Story song references: {len(song_offsets)}")
    print(f"Story catalog: {output}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("assets_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()
    convert(args.assets_root, args.output, args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
