#!/usr/bin/env python3
"""Compile song-script VideoCutscene references into a compact PS2 map."""

from __future__ import annotations

import argparse
import json
import re
import struct
from pathlib import Path

MAGIC = b"FCMP"
VERSION = 1
HEADER = struct.Struct("<4sHHII")
ENTRY = struct.Struct("<III")
FLAG_PRESONG = 1 << 0
FLAG_STORY_ONLY = 1 << 1

DIRECT_VIDEO = re.compile(r"Paths\.videos\(\s*['\"]([^'\"]+)['\"]\s*\)")
VIDEO_VAR = re.compile(r"(?:var\s+)?videoPath\s*=\s*['\"]([^'\"]+)['\"]")
VIDEO_PLAY = re.compile(r"VideoCutscene\.play\s*\(")


def add_string(blob: bytearray, cache: dict[str, int], text: str) -> int:
    if text in cache:
        return cache[text]
    offset = len(blob)
    blob.extend(text.encode("utf-8") + b"\0")
    cache[text] = offset
    return offset


def script_roots(assets_root: Path) -> list[Path]:
    roots = []
    for candidate in (
        assets_root / "scripts" / "songs",
        assets_root / "scripts",
    ):
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    return roots


def discover(assets_root: Path) -> list[dict]:
    found: dict[tuple[str, str], dict] = {}
    for root in script_roots(assets_root):
        for script in sorted(root.rglob("*.hxc")):
            text = script.read_text(encoding="utf-8-sig", errors="replace")
            if not VIDEO_PLAY.search(text):
                continue
            song_id = script.stem
            videos = DIRECT_VIDEO.findall(text)
            if not videos:
                match = VIDEO_VAR.search(text)
                if match:
                    videos = [match.group(1)]
            for video in videos:
                key = (song_id, video)
                found[key] = {
                    "songId": song_id,
                    "cutsceneId": video,
                    "flags": FLAG_PRESONG | FLAG_STORY_ONLY,
                    "source": script.relative_to(assets_root).as_posix(),
                }
    return sorted(found.values(), key=lambda item: (item["songId"], item["cutsceneId"]))


def convert(assets_root: Path, output: Path, manifest: Path | None = None) -> dict:
    assets_root = assets_root.resolve()
    entries = discover(assets_root)
    strings = bytearray()
    cache: dict[str, int] = {}
    records = bytearray()
    for item in entries:
        records.extend(ENTRY.pack(
            add_string(strings, cache, item["songId"]),
            add_string(strings, cache, item["cutsceneId"]),
            item["flags"],
        ))
    header = HEADER.pack(MAGIC, VERSION, len(entries), ENTRY.size, len(strings))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(header + records + strings)
    result = {
        "format": "FNF PS2 Cutscene Map",
        "entries": entries,
        "count": len(entries),
        "binary": output.as_posix(),
    }
    if manifest is not None:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"cutscene map entries: {len(entries)}")
    return result


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
