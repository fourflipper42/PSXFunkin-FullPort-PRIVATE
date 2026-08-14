#!/usr/bin/env python3
"""Validate the final generated XA enums, tables, paths, and Weekend intro route."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def enum_names(text: str, typedef: str) -> list[str]:
    match = re.search(r"typedef enum\s*\{([^}]*)\}\s*" + re.escape(typedef) + r"\s*;", text, re.S)
    if not match:
        raise SystemExit(f"missing {typedef} enum")
    body = re.sub(r"//.*", "", match.group(1))
    names = []
    for item in body.split(","):
        name = item.strip().split("=", 1)[0].strip()
        if name.startswith("XA_") and name != "XA_Max":
            names.append(name)
    return names


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path)
    args = parser.parse_args()
    audio_h = (args.upstream / "src/audio.h").read_text()
    audio_c = (args.upstream / "src/audio.c").read_text()
    weekend = (args.upstream / "src/stage/weekend1.c").read_text()

    files = enum_names(audio_h, "XA_File")
    tracks = enum_names(audio_h, "XA_Track")
    rows = re.findall(r"\{\s*(XA_[A-Za-z0-9_]+)\s*,[^\n]+\}\s*,?\s*//\s*(XA_[A-Za-z0-9_]+)", audio_c)
    if len(rows) != len(tracks):
        raise SystemExit(f"XA track table count mismatch: enum={len(tracks)} rows={len(rows)}")
    row_by_track = {tracks[index]: rows[index] for index in range(len(tracks))}
    for index, track in enumerate(tracks):
        if rows[index][1] != track:
            raise SystemExit(f"XA track index {index} comment mismatch: {track} != {rows[index][1]}")

    path_rows = re.findall(r'"(\\\\MUSIC\\\\[^";]+;1)"\s*,\s*//\s*(XA_[A-Za-z0-9_]+)', audio_c)
    if len(path_rows) != len(files):
        raise SystemExit(f"XA file path count mismatch: enum={len(files)} paths={len(path_rows)}")
    for index, name in enumerate(files):
        if path_rows[index][1] != name:
            raise SystemExit(f"XA file index {index} comment mismatch: {name} != {path_rows[index][1]}")

    expected = {
        "XA_DarnellIntro": ("XA_DarnIn", r"\\MUSIC\\DARNIN.XA;1"),
        "XA_Spaghetti": ("XA_Sserafim", r"\\MUSIC\\SPAG.XA;1"),
    }
    for track, (file_name, path) in expected.items():
        if row_by_track.get(track, (None,))[0] != file_name:
            raise SystemExit(f"{track} maps to {row_by_track.get(track)}, expected {file_name}")
        file_index = files.index(file_name)
        if path_rows[file_index][0] != path:
            raise SystemExit(f"{file_name} maps to {path_rows[file_index][0]}, expected {path}")

    direct = 'Audio_PlayXA("\\\\MUSIC\\\\DARNIN.XA;1",0x40,0,false);'
    if direct not in weekend:
        raise SystemExit("Weekend intro is not hard-routed to DARNIN.XA")
    print("FINAL_XA_ROUTE_VALIDATION_OK: Darnell intro and Spaghetti are isolated")


if __name__ == "__main__":
    main()
