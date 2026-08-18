#!/usr/bin/env python3
"""Convert official FNF Sparrow character JSON + atlas into PS2 runtime data."""

from __future__ import annotations

import argparse
import importlib.util
import json
import struct
import sys
from pathlib import Path

HEADER = struct.Struct("<4sHHIIIfffffII")
ANIM = struct.Struct("<IIffHHIHH")
MAGIC = b"FCHR"
VERSION = 1
FLAG_FLIP_X = 1 << 0
FLAG_PIXEL = 1 << 1
ANIM_LOOPED = 1 << 0
ANIM_FLIP_X = 1 << 1
ANIM_FLIP_Y = 1 << 2
NO_STRING = 0xFFFFFFFF


def load_atlas_converter():
    path = Path(__file__).with_name("convert_sparrow_atlas.py")
    spec = importlib.util.spec_from_file_location("convert_sparrow_atlas", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def find_case_path(root: Path, relative_without_ext: str, suffix: str) -> Path:
    rel = Path(*relative_without_ext.replace("\\", "/").split("/"))
    direct = root / rel.with_suffix(suffix)
    if direct.exists():
        return direct

    wanted = (rel.as_posix() + suffix).lower()
    for candidate in root.rglob(f"*{suffix}"):
        try:
            candidate_rel = candidate.relative_to(root).as_posix().lower()
        except ValueError:
            continue
        if candidate_rel == wanted:
            return candidate
    raise FileNotFoundError(f"asset not found: {relative_without_ext}{suffix} under {root}")


def find_character_json(assets_root: Path, character_id: str) -> Path:
    data_root = assets_root / "data" / "characters"
    direct = data_root / f"{character_id}.json"
    if direct.exists():
        return direct
    target = f"{character_id}.json".lower()
    if data_root.is_dir():
        for candidate in data_root.glob("*.json"):
            if candidate.name.lower() == target:
                return candidate
    raise FileNotFoundError(f"character JSON not found: {character_id}")


def pair(value, default=(0.0, 0.0)) -> tuple[float, float]:
    if isinstance(value, list) and len(value) >= 2:
        return float(value[0]), float(value[1])
    return float(default[0]), float(default[1])


def add_string(strings: bytearray, cache: dict[str, int], value: str | None) -> int:
    if value is None:
        return NO_STRING
    if value in cache:
        return cache[value]
    offset = len(strings)
    strings.extend(value.encode("utf-8") + b"\0")
    cache[value] = offset
    return offset


def convert(assets_root: Path, character_id: str, output_dir: Path) -> dict:
    atlas_converter = load_atlas_converter()
    json_path = find_character_json(assets_root, character_id)
    data = json.loads(json_path.read_text(encoding="utf-8"))

    render_type = str(data.get("renderType") or "sparrow").lower()
    if render_type != "sparrow":
        raise ValueError(f"{character_id}: renderType {render_type!r} is not Sparrow")

    asset_path = data.get("assetPath")
    if not isinstance(asset_path, str) or not asset_path:
        raise ValueError(f"{character_id}: missing assetPath")

    images_root = assets_root / "images"
    png_path = find_case_path(images_root, asset_path, ".png")
    xml_path = find_case_path(images_root, asset_path, ".xml")

    output_dir.mkdir(parents=True, exist_ok=True)
    atlas_stem = output_dir / "ATLAS"
    texture_converter = atlas_converter.load_texture_converter()
    texture_converter.convert(png_path, atlas_stem.with_suffix(".FPTX"))
    frame_count = atlas_converter.convert_frames(xml_path, atlas_stem.with_suffix(".FATL"))

    strings = bytearray()
    string_cache: dict[str, int] = {}
    indices: list[int] = []
    anim_records = bytearray()

    animations = data.get("animations") or []
    for anim in animations:
        name = str(anim.get("name") or "")
        prefix = str(anim.get("prefix") or "")
        if not name or not prefix:
            continue
        if anim.get("assetPath") not in (None, "", asset_path):
            raise ValueError(
                f"{character_id}/{name}: per-animation assetPath requires MultiSparrow support"
            )

        name_off = add_string(strings, string_cache, name)
        prefix_off = add_string(strings, string_cache, prefix)
        off_x, off_y = pair(anim.get("offsets"))
        fps = max(1, min(240, int(anim.get("frameRate") or 24)))
        flags = 0
        if bool(anim.get("looped", False)):
            flags |= ANIM_LOOPED
        if bool(anim.get("flipX", False)):
            flags |= ANIM_FLIP_X
        if bool(anim.get("flipY", False)):
            flags |= ANIM_FLIP_Y

        index_start = len(indices)
        selected = anim.get("frameIndices") or []
        for value in selected:
            value = int(value)
            if not 0 <= value <= 0xFFFF:
                raise ValueError(f"{character_id}/{name}: frame index out of range: {value}")
            indices.append(value)

        anim_records.extend(
            ANIM.pack(
                name_off,
                prefix_off,
                off_x,
                off_y,
                fps,
                flags,
                index_start,
                len(selected),
                0,
            )
        )

    global_x, global_y = pair(data.get("offsets"))
    scale = float(data.get("scale") if data.get("scale") is not None else 1.0)
    sing_time = float(data.get("singTime") if data.get("singTime") is not None else 1.0)
    dance_every = float(data.get("danceEvery") if data.get("danceEvery") is not None else 1.0)
    flags = 0
    if bool(data.get("flipX", False)):
        flags |= FLAG_FLIP_X
    if bool(data.get("isPixel", False)):
        flags |= FLAG_PIXEL

    starting = data.get("startingAnimation") or "idle"
    starting_off = add_string(strings, string_cache, str(starting))
    header = HEADER.pack(
        MAGIC,
        VERSION,
        len(anim_records) // ANIM.size,
        len(strings),
        len(indices),
        starting_off,
        scale,
        global_x,
        global_y,
        sing_time,
        dance_every,
        flags,
        ANIM.size,
    )
    index_blob = struct.pack(f"<{len(indices)}H", *indices) if indices else b""
    config_path = output_dir / "CHAR.FCHR"
    config_path.write_bytes(header + anim_records + index_blob + strings)

    result = {
        "id": character_id,
        "name": data.get("name", character_id),
        "renderType": render_type,
        "assetPath": asset_path,
        "sourceJson": json_path.as_posix(),
        "sourcePng": png_path.as_posix(),
        "sourceXml": xml_path.as_posix(),
        "atlasFrames": frame_count,
        "animations": len(anim_records) // ANIM.size,
        "output": output_dir.as_posix(),
    }
    print(json.dumps(result, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("assets_root", type=Path)
    parser.add_argument("character_id")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    convert(args.assets_root.resolve(), args.character_id, args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
