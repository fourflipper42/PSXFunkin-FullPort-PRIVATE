#!/usr/bin/env python3
"""Convert FNF health icons plus per-character icon metadata for PS2.

Legacy icon strips remain one texture and modern Sparrow health icons are paged
through the same FATL/FPTX atlas path used by characters. Character metadata is
written as a tiny HEALTH.FHCM sidecar so costumes may reuse another icon ID.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import struct
import sys
from pathlib import Path

MAP_MAGIC = b"FHCM"
MAP_VERSION = 1
MAP_HEADER = struct.Struct("<4sHHIIfff")
MAP_PIXEL = 1 << 0
MAP_FLIP_X = 1 << 1
MAP_SHOULD_BOP = 1 << 2


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


def find_icon(images_root: Path, icon_id: str, suffix: str) -> Path | None:
    direct = images_root / "icons" / f"icon-{icon_id}{suffix}"
    if direct.exists():
        return direct
    wanted = f"icon-{icon_id}{suffix}".lower()
    root = images_root / "icons"
    if root.is_dir():
        for path in root.glob(f"*{suffix}"):
            if path.name.lower() == wanted:
                return path
    return None


def write_character_map(character_dir: Path, icon: dict) -> dict:
    icon_id = str(icon.get("id") or "face")
    flags = 0
    if bool(icon.get("isPixel", False)):
        flags |= MAP_PIXEL
    if bool(icon.get("flipX", False)):
        flags |= MAP_FLIP_X
    if bool(icon.get("shouldBop", True)):
        flags |= MAP_SHOULD_BOP
    scale = float(icon.get("scale") if icon.get("scale") is not None else 1.0)
    ox, oy = pair(icon.get("offsets"))
    strings = icon_id.encode("utf-8") + b"\0"
    blob = MAP_HEADER.pack(
        MAP_MAGIC,
        MAP_VERSION,
        flags,
        len(strings),
        0,
        scale,
        ox,
        oy,
    ) + strings
    character_dir.mkdir(parents=True, exist_ok=True)
    (character_dir / "HEALTH.FHCM").write_bytes(blob)
    return {
        "id": icon_id,
        "isPixel": bool(flags & MAP_PIXEL),
        "flipX": bool(flags & MAP_FLIP_X),
        "shouldBop": bool(flags & MAP_SHOULD_BOP),
        "scale": scale,
        "offsets": [ox, oy],
    }


def convert(
    assets_root: Path,
    character_ids: list[str],
    output_root: Path,
    strict: bool = False,
) -> dict:
    texture_converter = load_module("convert_texture.py", "convert_texture_health_icons")
    atlas_converter = load_module("convert_sparrow_atlas.py", "convert_sparrow_health_icons")

    assets_root = assets_root.resolve()
    images_root = assets_root / "images"
    char_root = assets_root / "data" / "characters"
    output_root = output_root.resolve()
    icon_ids: dict[str, dict] = {}
    character_maps: dict[str, dict] = {}
    failures: list[str] = []

    for character_id in sorted(set(character_ids)):
        path = char_root / f"{character_id}.json"
        if not path.exists():
            failures.append(f"character metadata missing: {character_id}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("healthIcon")
            if isinstance(raw, str):
                icon = {"id": raw}
            elif isinstance(raw, dict):
                icon = dict(raw)
            else:
                icon = {"id": "face"}
            info = write_character_map(output_root / "CHAR" / character_id, icon)
            character_maps[character_id] = info
            icon_ids.setdefault(info["id"], info)
        except Exception as exc:
            failures.append(f"character {character_id}: {exc}")

    converted_icons: list[dict] = []
    for icon_id, map_info in sorted(icon_ids.items()):
        try:
            png = find_icon(images_root, icon_id, ".png")
            if png is None and icon_id != "face":
                png = find_icon(images_root, "face", ".png")
            if png is None:
                raise FileNotFoundError(f"images/icons/icon-{icon_id}.png")
            xml = find_icon(images_root, icon_id, ".xml")
            out_dir = output_root / "ICON" / icon_id
            out_dir.mkdir(parents=True, exist_ok=True)
            if xml is not None:
                frames, pages = atlas_converter.convert(png, xml, out_dir / "ICON")
                converted_icons.append({
                    "id": icon_id,
                    "kind": "sparrow",
                    "frames": frames,
                    "pages": pages,
                    "source": png.as_posix(),
                })
            else:
                texture_converter.convert(png, out_dir / "ICON.FPTX")
                converted_icons.append({
                    "id": icon_id,
                    "kind": "legacy",
                    "isPixel": bool(map_info.get("isPixel", False)),
                    "source": png.as_posix(),
                })
        except Exception as exc:
            failures.append(f"icon {icon_id}: {exc}")

    result = {
        "characters": character_maps,
        "icons": converted_icons,
        "failures": failures,
    }
    manifest = output_root / "ICON" / "ICONIDX.JSON"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"health icon characters: {len(character_maps)}")
    print(f"health icons: {len(converted_icons)}")
    print(f"health icon failures: {len(failures)}")
    if strict and failures:
        raise RuntimeError("health icon conversion failures:\n" + "\n".join(failures))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("assets_root", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("characters", nargs="+")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    convert(args.assets_root, args.characters, args.output_root, args.strict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
