#!/usr/bin/env python3
"""Discover runtime assets from official song metadata and convert them for PS2."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


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
    parse_errors: list[str] = []

    for metadata_path in metadata_files(songs_root):
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
        }
        for value in song_chars.values():
            if value:
                characters.add(value)

        stage = str(play.get("stage") or "")
        note_style = str(play.get("noteStyle") or "")
        if stage:
            stages.add(stage)
        if note_style:
            note_styles.add(note_style)

        songs.append(
            {
                "metadata": metadata_path.relative_to(songs_root).as_posix(),
                "songName": metadata.get("songName", metadata_path.parent.name),
                "characters": song_chars,
                "stage": stage,
                "noteStyle": note_style,
                "difficulties": play.get("difficulties") or [],
                "songVariations": play.get("songVariations") or [],
            }
        )

    character_converter = load_module("convert_character.py", "convert_character")
    stage_converter = load_module("convert_stage.py", "convert_stage")

    converted_characters: list[dict] = []
    converted_stages: list[dict] = []
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

    manifest = {
        "songs": songs,
        "discovered": {
            "characters": sorted(characters),
            "stages": sorted(stages),
            "noteStyles": sorted(note_styles),
        },
        "converted": {
            "characters": converted_characters,
            "stages": converted_stages,
        },
        "failures": failures,
    }
    manifest_path = output_root / "GAMEIDX.JSON"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(
        f"discovered {len(characters)} characters, {len(stages)} stages, "
        f"{len(note_styles)} note styles from {len(songs)} metadata files"
    )
    print(f"conversion failures: {len(failures)}")
    print(f"manifest: {manifest_path}")

    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
