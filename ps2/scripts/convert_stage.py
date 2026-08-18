#!/usr/bin/env python3
"""Convert an official FNF stage JSON and its props into PS2 runtime assets.

Stage coordinates remain in FNF's native 1280x720/world-space units. The PS2
runtime applies its canonical 0.5 presentation scale when drawing to 640x360.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import struct
import sys
from pathlib import Path

MAGIC = b"FSTG"
VERSION = 1
NO_STRING = 0xFFFFFFFF

HEADER = struct.Struct("<4sHHIIIIfIII")
CHAR_SLOT = struct.Struct("<ffiffffffff")
PROP = struct.Struct("<iIfffffffffIHHII")
ANIM = struct.Struct("<IIffHHIHH")

PROP_FLIP_X = 1 << 0
PROP_FLIP_Y = 1 << 1
PROP_PIXEL = 1 << 2
PROP_ANIMATED = 1 << 3
PROP_HAS_COLOR = 1 << 4
PROP_BLEND_ADD = 1 << 5
PROP_BLEND_MULTIPLY = 1 << 6
PROP_BLEND_SCREEN = 1 << 7

ANIM_LOOPED = 1 << 0
ANIM_FLIP_X = 1 << 1
ANIM_FLIP_Y = 1 << 2


def load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def pair(value, default=(0.0, 0.0)) -> tuple[float, float]:
    if isinstance(value, list) and len(value) >= 2:
        return float(value[0]), float(value[1])
    return float(default[0]), float(default[1])


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
    raise FileNotFoundError(f"asset not found: {relative_without_ext}{suffix}")


def find_stage_json(assets_root: Path, stage_id: str) -> Path:
    root = assets_root / "data" / "stages"
    direct = root / f"{stage_id}.json"
    if direct.exists():
        return direct
    wanted = f"{stage_id}.json".lower()
    if root.is_dir():
        for path in root.glob("*.json"):
            if path.name.lower() == wanted:
                return path
    raise FileNotFoundError(f"stage JSON not found: {stage_id}")


def add_string(strings: bytearray, cache: dict[str, int], value: str | None) -> int:
    if value is None:
        return NO_STRING
    if value in cache:
        return cache[value]
    offset = len(strings)
    strings.extend(value.encode("utf-8") + b"\0")
    cache[value] = offset
    return offset


def encode_char_slot(data: dict | None) -> bytes:
    data = data or {}
    x, y = pair(data.get("position"))
    sx, sy = pair(data.get("scroll"), (1.0, 1.0))
    cx, cy = pair(data.get("cameraOffsets"))
    scale = float(data.get("scale") if data.get("scale") is not None else 1.0)
    alpha = float(data.get("alpha") if data.get("alpha") is not None else 1.0)
    angle = float(data.get("angle") if data.get("angle") is not None else 0.0)
    z = int(data.get("zIndex") if data.get("zIndex") is not None else 0)
    return CHAR_SLOT.pack(x, y, z, scale, cx, cy, sx, sy, alpha, angle, 0.0)


def blend_flags(value: object) -> int:
    text = str(value or "normal").lower()
    if text in ("add", "additive"):
        return PROP_BLEND_ADD
    if text in ("multiply", "mul"):
        return PROP_BLEND_MULTIPLY
    if text == "screen":
        return PROP_BLEND_SCREEN
    return 0


def color_to_u32(value: object) -> int:
    if not isinstance(value, str):
        return 0xFFFFFFFF
    text = value.strip().lstrip("#")
    if len(text) == 6:
        text += "FF"
    if len(text) != 8:
        return 0xFFFFFFFF
    try:
        r = int(text[0:2], 16)
        g = int(text[2:4], 16)
        b = int(text[4:6], 16)
        a = int(text[6:8], 16)
    except ValueError:
        return 0xFFFFFFFF
    return r | (g << 8) | (b << 16) | (a << 24)


def convert(assets_root: Path, stage_id: str, output_dir: Path) -> dict:
    texture_converter = load_module("convert_texture.py", "convert_texture")
    atlas_converter = load_module("convert_sparrow_atlas.py", "convert_sparrow_atlas")

    stage_json = find_stage_json(assets_root, stage_id)
    data = json.loads(stage_json.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    images_root = assets_root / "images"

    props = data.get("props") or []
    strings = bytearray()
    string_cache: dict[str, int] = {}
    prop_records = bytearray()
    anim_records = bytearray()
    indices: list[int] = []
    manifest_props: list[dict] = []

    for index, prop in enumerate(props):
        name = str(prop.get("name") or f"prop{index}")
        asset_path = prop.get("assetPath")
        if not isinstance(asset_path, str) or not asset_path:
            print(f"warning: stage {stage_id} prop {name!r} has no assetPath; skipped")
            continue

        prop_id = f"P{len(manifest_props):03d}"
        png = find_case_path(images_root, asset_path, ".png")
        animations = prop.get("animations") or []
        animated = bool(animations)
        out_stem = output_dir / prop_id

        if animated:
            xml = find_case_path(images_root, asset_path, ".xml")
            atlas_frames, atlas_pages = atlas_converter.convert(png, xml, out_stem)
        else:
            texture_converter.convert(png, out_stem.with_suffix(".FPTX"))
            atlas_frames = 0
            atlas_pages = 0

        name_off = add_string(strings, string_cache, name)
        starting = prop.get("startingAnimation")
        if starting is None and animations:
            starting = animations[0].get("name")
        starting_off = add_string(strings, string_cache, str(starting) if starting else None)

        anim_start = len(anim_records) // ANIM.size
        for anim in animations:
            anim_name = str(anim.get("name") or "")
            prefix = str(anim.get("prefix") or "")
            if not anim_name or not prefix:
                continue
            anim_name_off = add_string(strings, string_cache, anim_name)
            prefix_off = add_string(strings, string_cache, prefix)
            ox, oy = pair(anim.get("offsets"))
            fps = max(1, min(240, int(anim.get("frameRate") or 24)))
            aflags = 0
            if bool(anim.get("looped", False)):
                aflags |= ANIM_LOOPED
            if bool(anim.get("flipX", False)):
                aflags |= ANIM_FLIP_X
            if bool(anim.get("flipY", False)):
                aflags |= ANIM_FLIP_Y
            selected = [int(v) for v in (anim.get("frameIndices") or [])]
            index_start = len(indices)
            for value in selected:
                if not 0 <= value <= 0xFFFF:
                    raise ValueError(f"{stage_id}/{name}/{anim_name}: frame index {value} out of range")
                indices.append(value)
            anim_records.extend(
                ANIM.pack(
                    anim_name_off,
                    prefix_off,
                    ox,
                    oy,
                    fps,
                    aflags,
                    index_start,
                    len(selected),
                    0,
                )
            )
        anim_count = (len(anim_records) // ANIM.size) - anim_start

        x, y = pair(prop.get("position"))
        scale_x, scale_y = pair(prop.get("scale"), (1.0, 1.0))
        scroll_x, scroll_y = pair(prop.get("scroll"), (1.0, 1.0))
        alpha = float(prop.get("alpha") if prop.get("alpha") is not None else 1.0)
        angle = float(prop.get("angle") if prop.get("angle") is not None else 0.0)
        dance_every = float(prop.get("danceEvery") if prop.get("danceEvery") is not None else 1.0)
        z = int(prop.get("zIndex") if prop.get("zIndex") is not None else 0)
        flags = blend_flags(prop.get("blend"))
        if bool(prop.get("flipX", False)):
            flags |= PROP_FLIP_X
        if bool(prop.get("flipY", False)):
            flags |= PROP_FLIP_Y
        if bool(prop.get("isPixel", False)):
            flags |= PROP_PIXEL
        if animated:
            flags |= PROP_ANIMATED
        if prop.get("color") is not None:
            flags |= PROP_HAS_COLOR

        color = color_to_u32(prop.get("color"))
        prop_records.extend(
            PROP.pack(
                z,
                flags,
                x,
                y,
                scale_x,
                scale_y,
                scroll_x,
                scroll_y,
                alpha,
                angle,
                dance_every,
                starting_off,
                anim_count,
                0,
                anim_start,
                color,
            )
        )
        manifest_props.append(
            {
                "id": prop_id,
                "name": name,
                "assetPath": asset_path,
                "animated": animated,
                "atlasFrames": atlas_frames,
                "atlasPages": atlas_pages,
                "animations": anim_count,
                "zIndex": z,
            }
        )

    characters = data.get("characters") or {}
    camera_zoom = float(data.get("cameraZoom") if data.get("cameraZoom") is not None else 1.0)
    flags = 0
    header = HEADER.pack(
        MAGIC,
        VERSION,
        len(manifest_props),
        len(strings),
        len(anim_records) // ANIM.size,
        len(indices),
        flags,
        camera_zoom,
        PROP.size,
        ANIM.size,
        CHAR_SLOT.size,
    )
    index_blob = struct.pack(f"<{len(indices)}H", *indices) if indices else b""
    blob = (
        header
        + encode_char_slot(characters.get("bf"))
        + encode_char_slot(characters.get("dad"))
        + encode_char_slot(characters.get("gf"))
        + prop_records
        + anim_records
        + index_blob
        + strings
    )
    (output_dir / "STAGE.FSTG").write_bytes(blob)

    manifest = {
        "id": stage_id,
        "cameraZoom": camera_zoom,
        "source": stage_json.as_posix(),
        "characters": characters,
        "props": manifest_props,
        "binaryBytes": len(blob),
    }
    (output_dir / "STAGE.JSON").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("assets_root", type=Path)
    parser.add_argument("stage_id")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    convert(args.assets_root.resolve(), args.stage_id, args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
