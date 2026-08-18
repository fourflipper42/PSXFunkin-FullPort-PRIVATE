#!/usr/bin/env python3
"""Convert FNF character JSON + supported atlas types into PS2 runtime data.

Sparrow sheets are repacked directly. AnimateAtlas/MultiAnimateAtlas characters
are baked from their hierarchical Adobe Animate timelines into stable, trimmed
frames first, then use the same paged runtime atlas format.
"""

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


def load_converter(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
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


def find_case_directory(root: Path, relative: str) -> Path:
    rel = Path(*relative.replace("\\", "/").split("/"))
    direct = root / rel
    if direct.is_dir():
        return direct
    wanted = rel.as_posix().lower()
    for candidate in root.rglob("*"):
        if not candidate.is_dir():
            continue
        try:
            candidate_rel = candidate.relative_to(root).as_posix().lower()
        except ValueError:
            continue
        if candidate_rel == wanted:
            return candidate
    raise FileNotFoundError(f"asset directory not found: {relative} under {root}")


def asset_root_and_relative(assets_root: Path, asset_path: str) -> tuple[Path, str]:
    if ":" not in asset_path:
        return assets_root / "images", asset_path
    prefix, relative = asset_path.split(":", 1)
    prefix = prefix.lower()
    if prefix == "shared":
        return assets_root / "shared" / "images", relative
    if prefix in ("preload", "default"):
        return assets_root / "images", relative
    # Mod-specific libraries may be flattened by import_user_modpack.py. Fall
    # back to the normal image root before rejecting the path outright.
    return assets_root / "images", relative


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
    sparrow_converter = load_converter("convert_sparrow_atlas.py", "convert_sparrow_atlas_character")
    animate_converter = load_converter("convert_animate_atlas.py", "convert_animate_atlas_character")
    json_path = find_character_json(assets_root, character_id)
    data = json.loads(json_path.read_text(encoding="utf-8"))

    render_type = str(data.get("renderType") or "sparrow").lower()
    asset_path = data.get("assetPath")
    if not isinstance(asset_path, str) or not asset_path:
        raise ValueError(f"{character_id}: missing assetPath")

    animations = data.get("animations") or []
    prefixes = [str(anim.get("prefix") or "") for anim in animations if anim.get("prefix")]
    root, relative = asset_root_and_relative(assets_root, asset_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    atlas_stem = output_dir / "ATLAS"
    source_info: dict[str, object] = {}
    default_fps = 24

    if render_type == "sparrow":
        png_path = find_case_path(root, relative, ".png")
        xml_path = find_case_path(root, relative, ".xml")
        frame_count, page_count = sparrow_converter.convert(png_path, xml_path, atlas_stem)
        source_info = {
            "sourcePng": png_path.as_posix(),
            "sourceXml": xml_path.as_posix(),
        }
    elif render_type in ("animateatlas", "multianimateatlas"):
        folder = find_case_directory(root, relative)
        frame_count, page_count, animate_info = animate_converter.convert(folder, prefixes, atlas_stem)
        default_fps = max(1, min(240, int(round(float(animate_info.get("frameRate", 24))))))
        source_info = {
            "sourceAnimateFolder": folder.as_posix(),
            "animateBake": animate_info,
        }
    else:
        raise ValueError(f"{character_id}: unsupported renderType {render_type!r}")

    strings = bytearray()
    string_cache: dict[str, int] = {}
    indices: list[int] = []
    anim_records = bytearray()

    for anim in animations:
        name = str(anim.get("name") or "")
        prefix = str(anim.get("prefix") or "")
        if not name or not prefix:
            continue
        per_asset = anim.get("assetPath")
        if per_asset not in (None, "", asset_path):
            raise ValueError(
                f"{character_id}/{name}: per-animation assetPath is not yet supported"
            )

        name_off = add_string(strings, string_cache, name)
        prefix_off = add_string(strings, string_cache, prefix)
        off_x, off_y = pair(anim.get("offsets"))
        fps = max(1, min(240, int(anim.get("frameRate") or default_fps)))
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
        **source_info,
        "atlasFrames": frame_count,
        "atlasPages": page_count,
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
