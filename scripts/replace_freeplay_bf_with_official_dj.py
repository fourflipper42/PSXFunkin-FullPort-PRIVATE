#!/usr/bin/env python3
"""Flatten the official v0.8.4 Boyfriend DJ Animate symbol into PS1 frames.

This does not create replacement artwork. It reconstructs four compatibility
samples of the existing 14-frame `Boyfriend DJ` idle symbol from Funkin's
shipped Animation.json, spritemap1.json, and spritemap1.png, then hands off to
the full-frame stream builder so runtime can animate every official frame.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

from PIL import Image

import build_v084_menu_visual_assets as base

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
DJ_SAMPLE_FRAMES = (0, 4, 8, 12)


def mat_mul(a: Matrix, b: Matrix) -> Matrix:
    aa, ab, ac, ad, atx, aty = a
    ba, bb, bc, bd, btx, bty = b
    return (
        aa * ba + ac * bb,
        ab * ba + ad * bb,
        aa * bc + ac * bd,
        ab * bc + ad * bd,
        aa * btx + ac * bty + atx,
        ab * btx + ad * bty + aty,
    )


def point(m: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, tx, ty = m
    return a * x + c * y + tx, b * x + d * y + ty


def symbol_duration(symbol: dict) -> int:
    return max(
        (frame.get("I", 0) + frame.get("DU", 1)
         for layer in symbol["TL"].get("L", [])
         for frame in layer.get("FR", [])),
        default=1,
    )


def active_frame(layer: dict, frame_no: int) -> dict | None:
    for frame in layer.get("FR", []):
        start = int(frame.get("I", 0))
        if start <= frame_no < start + int(frame.get("DU", 1)):
            return frame
    return None


def collect_leaves(
    symbols: dict[str, dict],
    symbol_name: str,
    frame_no: int,
    parent: Matrix = IDENTITY,
    out: list[tuple[str, Matrix]] | None = None,
    depth: int = 0,
) -> list[tuple[str, Matrix]]:
    if out is None:
        out = []
    if depth > 24:
        raise RuntimeError(f"Animate symbol recursion too deep at {symbol_name}")

    symbol = symbols[symbol_name]
    duration = symbol_duration(symbol)
    frame_no %= max(1, duration)

    # Animate JSON lists front layers first. Render back-to-front.
    for layer in reversed(symbol["TL"].get("L", [])):
        frame = active_frame(layer, frame_no)
        if frame is None:
            continue
        for element in reversed(frame.get("E", [])):
            if "ASI" in element:
                asi = element["ASI"]
                mx = tuple(float(v) for v in asi.get("MX", IDENTITY))
                out.append((str(asi["N"]), mat_mul(parent, mx)))
            elif "SI" in element:
                si = element["SI"]
                child = si["SN"]
                if child not in symbols:
                    continue
                mx = tuple(float(v) for v in si.get("MX", IDENTITY))
                first = int(si.get("FF", 0) or 0)
                # Graphic symbols are synchronized to their containing timeline.
                # Movie-clip helper symbols in this asset are static wrappers.
                child_frame = frame_no + first if si.get("ST", "G") == "G" else first
                collect_leaves(
                    symbols, child, child_frame, mat_mul(parent, mx), out, depth + 1
                )
    return out


def render_dj_frame(
    atlas: Image.Image,
    sprites: dict[str, dict],
    symbols: dict[str, dict],
    frame_no: int,
) -> Image.Image:
    leaves = collect_leaves(symbols, "Boyfriend DJ", frame_no)
    bounds: list[tuple[float, float]] = []
    for name, matrix in leaves:
        sprite = sprites[name]
        for x, y in ((0, 0), (sprite["w"], 0), (0, sprite["h"]), (sprite["w"], sprite["h"])):
            bounds.append(point(matrix, x, y))

    min_x = math.floor(min(x for x, _ in bounds))
    min_y = math.floor(min(y for _, y in bounds))
    max_x = math.ceil(max(x for x, _ in bounds))
    max_y = math.ceil(max(y for _, y in bounds))
    width, height = max_x - min_x, max_y - min_y
    canvas = Image.new("RGBA", (width, height), base.TRANSPARENT)

    for name, matrix in leaves:
        sprite = sprites[name]
        crop = atlas.crop((
            int(sprite["x"]), int(sprite["y"]),
            int(sprite["x"] + sprite["w"]), int(sprite["y"] + sprite["h"]),
        ))
        if sprite.get("rotated"):
            crop = crop.transpose(Image.Transpose.ROTATE_90)

        a, b, c, d, tx, ty = matrix
        det = a * d - b * c
        if abs(det) < 1e-9:
            continue
        ia, ic = d / det, -c / det
        ib, inv_d = -b / det, a / det
        offset_x = ia * (min_x - tx) + ic * (min_y - ty)
        offset_y = ib * (min_x - tx) + inv_d * (min_y - ty)
        warped = crop.transform(
            (width, height),
            Image.Transform.AFFINE,
            (ia, ic, offset_x, ib, inv_d, offset_y),
            resample=Image.Resampling.BICUBIC,
        )
        canvas.alpha_composite(warped)

    return base.trim(canvas)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets-root", type=Path, required=True)
    ap.add_argument("--upstream", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    dj_root = args.assets_root / "images/freeplay/freeplay-boyfriend"
    anim_path = dj_root / "Animation.json"
    map_path = dj_root / "spritemap1.json"
    png_path = dj_root / "spritemap1.png"
    for path in (anim_path, map_path, png_path):
        if not path.is_file():
            raise SystemExit(f"missing official Boyfriend DJ source: {path}")

    animation = json.loads(anim_path.read_text())
    map_data = json.loads(map_path.read_text())
    atlas = Image.open(png_path).convert("RGBA")
    symbols = {s["SN"]: s for s in animation["SD"]["S"] if "SN" in s}
    sprites = {entry["SPRITE"]["name"]: entry["SPRITE"] for entry in map_data["ATLAS"]["SPRITES"]}
    if "Boyfriend DJ" not in symbols:
        raise SystemExit("official Animation.json has no Boyfriend DJ symbol")

    page = Image.new("RGBA", (256, 256), base.TRANSPARENT)
    slots = ((0, 0), (128, 0), (0, 128), (128, 128))
    for frame_no, (x, y) in zip(DJ_SAMPLE_FRAMES, slots):
        authentic_frame = render_dj_frame(atlas, sprites, symbols, frame_no)
        page.alpha_composite(base.fit(authentic_frame, (128, 128)), (x, y))

    menu_dir = args.upstream / "iso/menu"
    template = base.parse_tim_template(menu_dir / "title.tim")
    out = menu_dir / "fpchar.tim"
    base.encode_tim4(page, template, out)

    report = json.loads(args.report.read_text())
    report["outputs"]["fpchar.tim"] = {
        "template": "title",
        "size": [256, 256],
        "bytes": out.stat().st_size,
        "sha256": base.sha256(out),
        "content": "official Boyfriend DJ idle symbol, flattened from existing Animate metadata",
        "sample_frames": list(DJ_SAMPLE_FRAMES),
    }
    for rel in (
        "images/freeplay/freeplay-boyfriend/Animation.json",
        "images/freeplay/freeplay-boyfriend/spritemap1.json",
        "images/freeplay/freeplay-boyfriend/spritemap1.png",
    ):
        path = args.assets_root / rel
        report["sources"][rel] = {"sha256": base.sha256(path), "bytes": path.stat().st_size}
    report["policy"] = "official-v0.8.4-existing-files-only; DJ frames reconstructed from shipped Animate data; no replacement artwork"
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Reconstructed compatibility Boyfriend DJ samples {DJ_SAMPLE_FRAMES}")

    # Upgrade that compatibility page into the full authentic 14-frame stream.
    helper = Path(__file__).with_name("build_freeplay_dj_stream.py")
    subprocess.run([
        sys.executable, str(helper),
        "--assets-root", str(args.assets_root),
        "--upstream", str(args.upstream),
        "--report", str(args.report),
    ], check=True)


if __name__ == "__main__":
    main()
