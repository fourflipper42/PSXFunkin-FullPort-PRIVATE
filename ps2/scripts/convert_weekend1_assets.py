#!/usr/bin/env python3
"""Convert Weekend 1 dynamic gameplay/cutscene visuals for the PS2 runtime."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


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
        frames, pages = sparrow.convert(png, xml, output_dir / stem)
        converted[stem] = {
            "source": source_name,
            "frames": frames,
            "pages": pages,
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
