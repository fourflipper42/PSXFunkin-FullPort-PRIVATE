#!/usr/bin/env python3
"""Discover official FNF runtime assets and convert them for the PS2 port.

Besides characters/stages, this writes one compact FSON descriptor per
song/variation/difficulty plus GAME.FCAT, a binary catalog the PS2 runtime can
browse without parsing JSON or hard-coding song names.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import struct
import sys
from pathlib import Path

FSON_MAGIC = b"FSON"
FSON_VERSION = 1
FSON_HEADER = struct.Struct("<4sHHI10If")

FCAT_MAGIC = b"FCAT"
FCAT_VERSION = 1
FCAT_HEADER = struct.Struct("<4sHHIII")
FCAT_ENTRY = struct.Struct("<IIIII")

NO_STRING = 0xFFFFFFFF


def load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def find_songs_root(assets_root: Path) -> Path:
    direct = assets_root / "data" / "songs"
    if direct.is_dir():
        return direct
    raise FileNotFoundError(f"data/songs not found under {assets_root}")


def metadata_files(songs_root: Path) -> list[Path]:
    files: list[Path] = []
    for song_dir in songs_root.iterdir():
        if not song_dir.is_dir():
            continue
        for path in song_dir.glob("*.json"):
            if "metadata" in path.stem.lower():
                files.append(path)
    return sorted(files)


def variation_from_metadata(song_id: str, metadata_path: Path) -> str | None:
    prefix = f"{song_id}-metadata"
    stem = metadata_path.stem
    if not stem.lower().startswith(prefix.lower()):
        return None
    suffix = stem[len(prefix):]
    if not suffix:
        return "default"
    if suffix.startswith("-"):
        suffix = suffix[1:]
    return suffix or "default"


def chart_for_variation(song_dir: Path, song_id: str, variation: str) -> Path | None:
    suffix = "" if variation == "default" else f"-{variation}"
    wanted = f"{song_id}-chart{suffix}.json".lower()
    for path in song_dir.glob("*.json"):
        if path.name.lower() == wanted:
            return path
    return None


def add_string(strings: bytearray, cache: dict[str, int], value: str | None) -> int:
    if value is None or value == "":
        return NO_STRING
    if value in cache:
        return cache[value]
    offset = len(strings)
    strings.extend(value.encode("utf-8") + b"\0")
    cache[value] = offset
    return offset


def scroll_speed_for(chart: dict, difficulty: str) -> float:
    speeds = chart.get("scrollSpeed")
    if isinstance(speeds, dict):
        value = speeds.get(difficulty)
        if isinstance(value, (int, float)):
            return float(value)
        for fallback in ("normal", "default"):
            value = speeds.get(fallback)
            if isinstance(value, (int, float)):
                return float(value)
    if isinstance(speeds, (int, float)):
        return float(speeds)
    return 1.0


def write_song_descriptor(
    output_root: Path,
    song_id: str,
    display_name: str,
    variation: str,
    difficulty: str,
    stage: str,
    note_style: str,
    chars: dict,
    speed: float,
) -> Path:
    strings = bytearray()
    cache: dict[str, int] = {}
    values = [
        song_id,
        display_name,
        variation,
        difficulty,
        stage,
        note_style,
        str(chars.get("player") or ""),
        str(chars.get("girlfriend") or ""),
        str(chars.get("opponent") or ""),
        str(chars.get("instrumental") or ""),
    ]
    offsets = [add_string(strings, cache, value) for value in values]
    header = FSON_HEADER.pack(
        FSON_MAGIC,
        FSON_VERSION,
        0,
        len(strings),
        *offsets,
        float(speed),
    )
    out = output_root / "SONG" / song_id / variation / f"{difficulty}.FSON"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(header + strings)
    return out


def descriptor_disc_path(relative: str) -> str:
    return ("\\GAME\\" + relative.replace("/", "\\") + ";1").upper()


def write_song_catalog(output_root: Path, descriptors: list[dict]) -> Path:
    strings = bytearray()
    cache: dict[str, int] = {}
    records = bytearray()

    for item in descriptors:
        values = [
            str(item["song"]),
            str(item["displayName"]),
            str(item["variation"]),
            str(item["difficulty"]),
            descriptor_disc_path(str(item["file"])),
        ]
        offsets = [add_string(strings, cache, value) for value in values]
        if any(offset == NO_STRING for offset in offsets):
            raise ValueError(f"catalog entry contains an empty required string: {item}")
        records.extend(FCAT_ENTRY.pack(*offsets))

    header = FCAT_HEADER.pack(
        FCAT_MAGIC,
        FCAT_VERSION,
        0,
        len(descriptors),
        FCAT_ENTRY.size,
        len(strings),
    )
    path = output_root / "GAME.FCAT"
    path.write_bytes(header + records + strings)
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("assets_root", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--strict", action="store_true", help="Fail if any discovered asset cannot be converted")
    args = parser.parse_args()

    assets_root = args.assets_root.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    songs_root = find_songs_root(assets_root)

    characters: set[str] = set()
    stages: set[str] = set()
    note_styles: set[str] = set()
    songs: list[dict] = []
    descriptors: list[dict] = []
    parse_errors: list[str] = []

    for metadata_path in metadata_files(songs_root):
        song_id = metadata_path.parent.name
        variation = variation_from_metadata(song_id, metadata_path)
        if variation is None:
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception as exc:
            parse_errors.append(f"{metadata_path}: {exc}")
            continue

        play = metadata.get("playData") or {}
        chars = play.get("characters") or {}
        song_chars = {
            "player": str(chars.get("player") or ""),
            "girlfriend": str(chars.get("girlfriend") or ""),
            "opponent": str(chars.get("opponent") or ""),
            "instrumental": str(chars.get("instrumental") or ""),
        }
        for key in ("player", "girlfriend", "opponent"):
            value = song_chars[key]
            if value:
                characters.add(value)

        stage = str(play.get("stage") or "")
        note_style = str(play.get("noteStyle") or "")
        if stage:
            stages.add(stage)
        if note_style:
            note_styles.add(note_style)

        chart_path = chart_for_variation(metadata_path.parent, song_id, variation)
        chart: dict = {}
        if chart_path is None:
            parse_errors.append(f"{song_id}/{variation}: matching chart JSON not found")
        else:
            try:
                chart = json.loads(chart_path.read_text(encoding="utf-8"))
            except Exception as exc:
                parse_errors.append(f"{chart_path}: {exc}")

        notes = chart.get("notes") if isinstance(chart, dict) else None
        difficulties = sorted(notes.keys()) if isinstance(notes, dict) else []
        display_name = str(metadata.get("songName") or song_id)
        for difficulty in difficulties:
            if not isinstance(notes.get(difficulty), list):
                continue
            speed = scroll_speed_for(chart, difficulty)
            descriptor_path = write_song_descriptor(
                output_root,
                song_id,
                display_name,
                variation,
                difficulty,
                stage,
                note_style,
                song_chars,
                speed,
            )
            descriptors.append(
                {
                    "song": song_id,
                    "displayName": display_name,
                    "variation": variation,
                    "difficulty": difficulty,
                    "file": descriptor_path.relative_to(output_root).as_posix(),
                    "scrollSpeed": speed,
                }
            )

        songs.append(
            {
                "metadata": metadata_path.relative_to(songs_root).as_posix(),
                "songId": song_id,
                "songName": display_name,
                "variation": variation,
                "characters": song_chars,
                "stage": stage,
                "noteStyle": note_style,
                "difficulties": difficulties,
                "songVariations": play.get("songVariations") or [],
            }
        )

    character_converter = load_module("convert_character.py", "convert_character")
    stage_converter = load_module("convert_stage.py", "convert_stage")
    weekend1_converter = load_module("convert_weekend1_assets.py", "convert_weekend1_assets")

    converted_characters: list[dict] = []
    converted_stages: list[dict] = []
    weekend1_pack: dict | None = None
    failures: list[str] = list(parse_errors)

    for character_id in sorted(characters):
        try:
            result = character_converter.convert(
                assets_root,
                character_id,
                output_root / "CHAR" / character_id,
            )
            converted_characters.append(result)
        except Exception as exc:
            failures.append(f"character {character_id}: {exc}")
            print(f"ERROR character {character_id}: {exc}", file=sys.stderr)

    for stage_id in sorted(stages):
        try:
            result = stage_converter.convert(
                assets_root,
                stage_id,
                output_root / "STAGE" / stage_id,
            )
            converted_stages.append(result)
        except Exception as exc:
            failures.append(f"stage {stage_id}: {exc}")
            print(f"ERROR stage {stage_id}: {exc}", file=sys.stderr)

    if (assets_root.joinpath("weekend1", "images").is_dir()):
        try:
            weekend1_pack = weekend1_converter.convert(
                assets_root,
                output_root / "WEEKEND1",
            )
        except Exception as exc:
            failures.append(f"weekend1 dynamic assets: {exc}")
            print(f"ERROR weekend1 dynamic assets: {exc}", file=sys.stderr)

    catalog_path = write_song_catalog(output_root, descriptors)
    manifest = {
        "songs": songs,
        "songDescriptors": descriptors,
        "runtimeCatalog": catalog_path.relative_to(output_root).as_posix(),
        "discovered": {
            "characters": sorted(characters),
            "stages": sorted(stages),
            "noteStyles": sorted(note_styles),
        },
        "converted": {
            "characters": converted_characters,
            "stages": converted_stages,
            "weekend1": weekend1_pack,
        },
        "failures": failures,
    }
    manifest_path = output_root / "GAMEIDX.JSON"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(
        f"discovered {len(characters)} characters, {len(stages)} stages, "
        f"{len(note_styles)} note styles from {len(songs)} metadata files"
    )
    print(f"runtime song descriptors: {len(descriptors)}")
    print(f"runtime catalog: {catalog_path}")
    print(f"conversion failures: {len(failures)}")
    print(f"manifest: {manifest_path}")

    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
