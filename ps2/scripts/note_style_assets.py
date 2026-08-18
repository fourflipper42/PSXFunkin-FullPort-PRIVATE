#!/usr/bin/env python3
"""Helpers for locating modern FNF note-style data and namespaced artwork."""

from __future__ import annotations

from pathlib import Path


def find_note_style_json(assets_root: Path, style_id: str) -> Path:
    candidates = (
        assets_root / "data" / "notestyles" / f"{style_id}.json",
        assets_root / "preload" / "data" / "notestyles" / f"{style_id}.json",
        assets_root.parent / "preload" / "data" / "notestyles" / f"{style_id}.json",
    )
    for path in candidates:
        if path.is_file():
            return path

    wanted = f"{style_id}.json".lower()
    for base in (assets_root, assets_root.parent):
        if not base.exists():
            continue
        for path in base.rglob("*.json"):
            if path.name.lower() == wanted and path.parent.name.lower() == "notestyles":
                return path
    raise FileNotFoundError(f"note style JSON not found: {style_id}")


def split_asset_path(asset_path: str) -> tuple[str | None, str]:
    if ":" not in asset_path:
        return None, asset_path
    library, relative = asset_path.split(":", 1)
    return library.strip().lower() or None, relative.lstrip("/\\")


def find_asset(assets_root: Path, asset_path: str, suffix: str) -> Path:
    library, relative = split_asset_path(asset_path)
    rel = Path(*relative.replace("\\", "/").split("/"))
    candidates: list[Path] = []

    if library:
        names = [library]
        if library == "default":
            names.append("preload")
        for name in names:
            candidates += [
                assets_root / name / "images" / rel.with_suffix(suffix),
                assets_root.parent / name / "images" / rel.with_suffix(suffix),
            ]

    candidates += [
        assets_root / "images" / rel.with_suffix(suffix),
        assets_root / "shared" / "images" / rel.with_suffix(suffix),
        assets_root / "preload" / "images" / rel.with_suffix(suffix),
        assets_root.parent / "shared" / "images" / rel.with_suffix(suffix),
        assets_root.parent / "preload" / "images" / rel.with_suffix(suffix),
    ]
    for path in candidates:
        if path.is_file():
            return path

    wanted_tail = rel.with_suffix(suffix).as_posix().lower()
    fallback: list[Path] = []
    for base in (assets_root, assets_root.parent):
        if not base.exists():
            continue
        for path in base.rglob(f"*{suffix}"):
            normalized = path.as_posix().lower()
            if normalized.endswith(wanted_tail):
                if library and f"/{library}/" in normalized:
                    return path
                fallback.append(path)
    if fallback:
        return sorted(fallback)[0]
    raise FileNotFoundError(f"asset not found: {asset_path}{suffix}")
