#!/usr/bin/env python3
"""Discover every note style referenced by song metadata and convert it."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def load_converter():
    path = Path(__file__).with_name("convert_note_style.py")
    spec = importlib.util.spec_from_file_location("convert_note_style", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def discover_styles(assets_root: Path) -> set[str]:
    songs_root = assets_root / "data" / "songs"
    if not songs_root.is_dir():
        raise FileNotFoundError(f"data/songs not found under {assets_root}")

    styles: set[str] = set()
    for path in songs_root.rglob("*.json"):
        if "metadata" not in path.stem.lower():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        style = str((data.get("playData") or {}).get("noteStyle") or "").strip()
        if style:
            styles.add(style)
    return styles


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("assets_root", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()

    assets_root = args.assets_root.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    converter = load_converter()
    styles = sorted(discover_styles(assets_root))
    converted: list[dict] = []
    failures: list[str] = []

    for style_id in styles:
        try:
            converted.append(converter.convert(
                assets_root,
                style_id,
                output_root / style_id,
            ))
        except Exception as exc:
            failures.append(f"{style_id}: {exc}")
            print(f"ERROR note style {style_id}: {exc}", file=sys.stderr)

    manifest = {
        "discovered": styles,
        "converted": converted,
        "failures": failures,
    }
    manifest_path = args.manifest or (output_root / "NOTESTYLE.JSON")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"note styles: {len(styles)} discovered, {len(converted)} converted, {len(failures)} failed")

    if not styles:
        return 1
    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
