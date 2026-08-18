#!/usr/bin/env python3
"""Discover and convert every video cutscene in an FNF asset tree."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv", ".avi"}


def load_converter():
    path = Path(__file__).with_name("convert_cutscene_video.py")
    spec = importlib.util.spec_from_file_location("convert_cutscene_video_bulk", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def discover(assets_root: Path) -> list[Path]:
    videos = assets_root / "videos"
    if not videos.is_dir():
        return []
    return sorted(
        path for path in videos.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
    )


def safe_id(path: Path, root: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    text = "__".join(relative.parts)
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)


def convert_all(
    assets_root: Path,
    output_root: Path,
    manifest_path: Path | None,
    strict: bool,
) -> dict:
    assets_root = assets_root.resolve()
    output_root = output_root.resolve()
    videos_root = assets_root / "videos"
    converter = load_converter()
    converted: list[dict] = []
    failures: list[str] = []

    for video in discover(assets_root):
        cutscene_id = safe_id(video, videos_root)
        try:
            info = converter.convert(video, output_root / cutscene_id)
            info["id"] = cutscene_id
            info["assetStem"] = video.stem
            info["relativeSource"] = video.relative_to(assets_root).as_posix()
            converted.append(info)
        except Exception as exc:
            failures.append(f"{video}: {exc}")

    result = {
        "format": "FNF PS2 Cutscene Index",
        "cutscenes": converted,
        "failures": failures,
    }
    if manifest_path is not None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"cutscenes: {len(converted)}")
    print(f"cutscene failures: {len(failures)}")
    if strict and failures:
        raise RuntimeError("cutscene conversion failures:\n" + "\n".join(failures))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("assets_root", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    convert_all(args.assets_root, args.output_root, args.manifest, args.strict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
