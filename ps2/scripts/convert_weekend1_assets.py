#!/usr/bin/env python3
"""Convert Weekend 1 dynamic gameplay/cutscene visuals for the PS2 runtime."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

SHOT_EXPLOSION_BAKE_SCALE = 0.80


def load_converter(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def require(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def scaled_int(value: str | None, scale: float, minimum: int | None = None) -> str | None:
    if value is None or value == "":
        return value
    result = int(round(int(value) * scale))
    if minimum is not None and result < minimum:
        result = minimum
    return str(result)


def build_scaled_sparrow(
    png: Path,
    xml: Path,
    scale: float,
    temp_dir: Path,
) -> tuple[Path, Path]:
    """Bake an oversized Sparrow atlas smaller while preserving trim geometry.

    Runtime draws this one effect at 1/scale, so its authored world size remains
    approximately unchanged while every packed texture frame fits a PS2 page.
    """
    if not 0.0 < scale <= 1.0:
        raise ValueError(f"invalid Sparrow bake scale: {scale}")

    scaled_png = temp_dir / png.name
    scaled_xml = temp_dir / xml.name

    with Image.open(png) as source:
        rgba = source.convert("RGBA")
        width = max(1, int(round(rgba.width * scale)))
        height = max(1, int(round(rgba.height * scale)))
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        rgba.resize((width, height), resampling).save(scaled_png)

    tree = ET.parse(xml)
    root = tree.getroot()
    root.set("imagePath", scaled_png.name)
    for frame in root.findall(".//SubTexture"):
        for key in ("x", "y", "frameX", "frameY"):
            value = scaled_int(frame.get(key), scale)
            if value is not None:
                frame.set(key, value)
        for key in ("width", "height", "frameWidth", "frameHeight"):
            value = scaled_int(frame.get(key), scale, 1)
            if value is not None:
                frame.set(key, value)
    tree.write(scaled_xml, encoding="utf-8", xml_declaration=True)
    return scaled_png, scaled_xml


def convert(assets_root: Path, output_dir: Path) -> dict:
    animate = load_converter("convert_animate_atlas.py", "convert_weekend1_animate")
    sparrow = load_converter("convert_sparrow_atlas.py", "convert_weekend1_sparrow")

    images = require(assets_root / "weekend1" / "images")
    output_dir.mkdir(parents=True, exist_ok=True)

    can_folder = require(images / "spraycanAtlas")
    can_frames, can_pages, can_info = animate.convert(
        can_folder,
        ["Can Start", "Can Shot", "Hit Pico"],
        output_dir / "CAN",
    )

    sparrow_assets = {
        "SHOTEXP": "SpraypaintExplosion",
        "IMPACTEXP": "spraypaintExplosionEZ",
        "IMPACT": "CanImpactParticle",
        "INTROCAN": "wked1_cutscene_1_can",
    }
    converted = {}
    for stem, source_name in sparrow_assets.items():
        png = require(images / f"{source_name}.png")
        xml = require(images / f"{source_name}.xml")
        bake_scale = 1.0

        if stem == "SHOTEXP":
            bake_scale = SHOT_EXPLOSION_BAKE_SCALE
            with tempfile.TemporaryDirectory(prefix="fnf-ps2-weekend1-") as temp:
                scaled_png, scaled_xml = build_scaled_sparrow(
                    png, xml, bake_scale, Path(temp)
                )
                frames, pages = sparrow.convert(
                    scaled_png, scaled_xml, output_dir / stem
                )
        else:
            frames, pages = sparrow.convert(png, xml, output_dir / stem)

        converted[stem] = {
            "source": source_name,
            "frames": frames,
            "pages": pages,
            "bakeScale": bake_scale,
            "runtimeScaleCompensation": 1.0 / bake_scale,
        }

    result = {
        "format": "FNF PS2 Weekend 1 Visual Pack",
        "can": {
            "source": can_folder.as_posix(),
            "frames": can_frames,
            "pages": can_pages,
            "animateBake": can_info,
        },
        "sparrow": converted,
    }
    manifest = output_dir / "WEEKEND1.JSON"
    manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("assets_root", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    convert(args.assets_root.resolve(), args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
