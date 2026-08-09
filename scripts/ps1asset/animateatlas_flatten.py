#!/usr/bin/env python3
"""Flatten Adobe Animate texture-atlas timelines into authentic RGBA frames.

The converter reads Animation.json, spritemap1.json and spritemap1.png. It
recursively evaluates supplied symbols and matrices; it never creates in-between
frames or fills missing animations. Output frames therefore remain direct
renderings of the source package.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def matrix_from_element(data: dict[str, Any]) -> Matrix:
    raw = data.get("M3D") or data.get("MX")
    if raw is None:
        return IDENTITY
    if isinstance(raw, list) and len(raw) >= 16:
        return (float(raw[0]), float(raw[1]), float(raw[4]), float(raw[5]), float(raw[12]), float(raw[13]))
    if isinstance(raw, list) and len(raw) >= 6:
        return tuple(float(v) for v in raw[:6])  # type: ignore[return-value]
    raise ValueError(f"Unsupported matrix: {raw!r}")


def multiply(parent: Matrix, local: Matrix) -> Matrix:
    pa, pb, pc, pd, ptx, pty = parent
    la, lb, lc, ld, ltx, lty = local
    return (
        pa * la + pc * lb,
        pb * la + pd * lb,
        pa * lc + pc * ld,
        pb * lc + pd * ld,
        pa * ltx + pc * lty + ptx,
        pb * ltx + pd * lty + pty,
    )


def transform_point(m: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, tx, ty = m
    return a * x + c * y + tx, b * x + d * y + ty


def invert(m: Matrix) -> Matrix:
    a, b, c, d, tx, ty = m
    det = a * d - b * c
    if abs(det) < 1e-12:
        raise ValueError("Singular transform")
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return ia, ib, ic, id_, -(ia * tx + ic * ty), -(ib * tx + id_ * ty)


def safe_name(value: str) -> str:
    value = value.strip().lower().replace(" ", "_")
    value = re.sub(r"[^a-z0-9_.-]+", "_", value)
    return value.strip("_") or "frame"


@dataclass
class Leaf:
    name: str
    image: Image.Image
    matrix: Matrix
    alpha: float = 1.0


class AnimateAtlas:
    def __init__(self, folder: Path):
        self.folder = folder
        self.anim = load_json(folder / "Animation.json")
        self.map = load_json(folder / "spritemap1.json")
        image_name = self.map.get("meta", {}).get("image", "spritemap1.png")
        self.sheet = Image.open(folder / image_name).convert("RGBA")
        self.symbols = {s["SN"]: s for s in self.anim.get("SD", {}).get("S", [])}
        self.sprites: dict[str, Image.Image] = {}
        for item in self.map["ATLAS"]["SPRITES"]:
            s = item["SPRITE"]
            x, y, w, h = (int(s[k]) for k in ("x", "y", "w", "h"))
            img = self.sheet.crop((x, y, x + w, y + h))
            if s.get("rotated"):
                img = img.transpose(Image.Transpose.ROTATE_90)
            self.sprites[str(s["name"])] = img
        self.root = self.anim["AN"]
        self.frame_rate = float(self.anim.get("MD", {}).get("FRT", 24.0))

    @staticmethod
    def timeline_length(timeline: dict[str, Any]) -> int:
        return max((int(fr["I"]) + int(fr.get("DU", 1))
                    for layer in timeline.get("L", [])
                    for fr in layer.get("FR", [])), default=0)

    @staticmethod
    def active_keyframe(layer: dict[str, Any], frame: int) -> dict[str, Any] | None:
        for key in layer.get("FR", []):
            start = int(key["I"])
            if start <= frame < start + int(key.get("DU", 1)):
                return key
        return None

    @staticmethod
    def alpha_from_color(data: dict[str, Any]) -> float:
        c = data.get("C")
        if not isinstance(c, dict):
            return 1.0
        return max(0.0, min(1.0, float(c.get("AM", 1.0))))

    def _render_timeline(self, timeline: dict[str, Any], frame: int, parent: Matrix,
                         parent_alpha: float, stack: tuple[str, ...]) -> list[Leaf]:
        leaves: list[Leaf] = []
        for layer in reversed(timeline.get("L", [])):
            if str(layer.get("LT", "")).lower() in {"clp", "clipper"}:
                continue
            key = self.active_keyframe(layer, frame)
            if key is None:
                continue
            local_frame = frame - int(key["I"])
            for elem in key.get("E", []):
                if "ASI" in elem:
                    asi = elem["ASI"]
                    name = str(asi["N"])
                    image = self.sprites.get(name)
                    if image is None:
                        raise KeyError(f"Atlas sprite {name!r} not found")
                    matrix = multiply(parent, matrix_from_element(asi))
                    leaves.append(Leaf(name, image, matrix, parent_alpha * self.alpha_from_color(asi)))
                elif "SI" in elem:
                    si = elem["SI"]
                    name = str(si["SN"])
                    if name in stack:
                        raise ValueError(f"Recursive symbol cycle: {' -> '.join(stack + (name,))}")
                    symbol = self.symbols.get(name)
                    if symbol is None:
                        raise KeyError(f"Symbol {name!r} not found")
                    child_timeline = symbol["TL"]
                    length = max(1, self.timeline_length(child_timeline))
                    child_frame = local_frame + int(si.get("FF", 0))
                    loop = str(si.get("LP", "LP")).upper()
                    if loop.startswith("SF"):
                        child_frame = int(si.get("FF", 0))
                    elif loop.startswith("PO"):
                        child_frame = min(max(child_frame, 0), length - 1)
                    else:
                        child_frame %= length
                    matrix = multiply(parent, matrix_from_element(si))
                    leaves.extend(self._render_timeline(child_timeline, child_frame, matrix,
                        parent_alpha * self.alpha_from_color(si), stack + (name,)))
        return leaves

    def leaves_for_frame(self, frame: int) -> list[Leaf]:
        length = self.timeline_length(self.root["TL"])
        if not 0 <= frame < length:
            raise IndexError(f"Frame {frame} outside 0..{length - 1}")
        return self._render_timeline(self.root["TL"], frame, IDENTITY, 1.0, (self.root.get("SN", "root"),))

    def labels(self) -> list[dict[str, Any]]:
        labels: list[dict[str, Any]] = []
        for layer in self.root["TL"].get("L", []):
            for fr in layer.get("FR", []):
                if fr.get("N"):
                    labels.append({"name": str(fr["N"]), "start": int(fr["I"]), "duration": int(fr.get("DU", 1))})
        labels.sort(key=lambda x: x["start"])
        return labels


def leaf_bounds(leaf: Leaf) -> tuple[float, float, float, float]:
    w, h = leaf.image.size
    pts = [transform_point(leaf.matrix, x, y) for x, y in ((0, 0), (w, 0), (0, h), (w, h))]
    xs, ys = zip(*pts)
    return min(xs), min(ys), max(xs), max(ys)


def render_leaves(leaves: Iterable[Leaf], padding: int = 2) -> tuple[Image.Image, tuple[int, int]]:
    leaves = list(leaves)
    if not leaves:
        return Image.new("RGBA", (1, 1)), (0, 0)
    bounds = [leaf_bounds(l) for l in leaves]
    min_x = math.floor(min(b[0] for b in bounds)) - padding
    min_y = math.floor(min(b[1] for b in bounds)) - padding
    max_x = math.ceil(max(b[2] for b in bounds)) + padding
    max_y = math.ceil(max(b[3] for b in bounds)) + padding
    width, height = max(1, max_x - min_x), max(1, max_y - min_y)
    out = Image.new("RGBA", (width, height))
    shift: Matrix = (1, 0, 0, 1, -min_x, -min_y)
    for leaf in leaves:
        forward = multiply(shift, leaf.matrix)
        inv = invert(forward)
        coeffs = (inv[0], inv[2], inv[4], inv[1], inv[3], inv[5])
        transformed = leaf.image.transform((width, height), Image.Transform.AFFINE, coeffs,
            resample=Image.Resampling.BICUBIC)
        if leaf.alpha < 0.999:
            alpha = transformed.getchannel("A").point(lambda v: round(v * leaf.alpha))
            transformed.putalpha(alpha)
        out.alpha_composite(transformed)
    return out, (min_x, min_y)


def render_leaves_fixed(leaves: Iterable[Leaf], size: tuple[int, int], transform: Matrix) -> Image.Image:
    width, height = size
    out = Image.new("RGBA", size)
    for leaf in leaves:
        forward = multiply(transform, leaf.matrix)
        inv = invert(forward)
        coeffs = (inv[0], inv[2], inv[4], inv[1], inv[3], inv[5])
        transformed = leaf.image.transform((width, height), Image.Transform.AFFINE, coeffs,
            resample=Image.Resampling.BICUBIC)
        if leaf.alpha < 0.999:
            alpha = transformed.getchannel("A").point(lambda v: round(v * leaf.alpha))
            transformed.putalpha(alpha)
        out.alpha_composite(transformed)
    return out


def export(atlas: AnimateAtlas, output: Path, labels_only: bool, scale: float) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    all_labels = atlas.labels()
    ranges = all_labels if labels_only and all_labels else [
        {"name": "timeline", "start": 0, "duration": atlas.timeline_length(atlas.root["TL"])}]
    manifest: dict[str, Any] = {
        "source": str(atlas.folder), "frame_rate": atlas.frame_rate,
        "timeline_frames": atlas.timeline_length(atlas.root["TL"]),
        "labels": all_labels, "exports": []}
    for label in ranges:
        label_dir = output / safe_name(label["name"])
        label_dir.mkdir(exist_ok=True)
        for relative in range(label["duration"]):
            absolute = label["start"] + relative
            image, origin = render_leaves(atlas.leaves_for_frame(absolute))
            if scale != 1.0:
                image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
            path = label_dir / f"{relative:04d}.png"
            image.save(path, optimize=True)
            manifest["exports"].append({
                "label": label["name"], "relative_frame": relative,
                "source_frame": absolute, "path": str(path.relative_to(output)),
                "origin": list(origin), "size": list(image.size),
                "leaf_count": len(atlas.leaves_for_frame(absolute))})
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--all-frames", action="store_true")
    parser.add_argument("--scale", type=float, default=1.0)
    args = parser.parse_args()
    manifest = export(AnimateAtlas(args.folder), args.output, not args.all_frames, args.scale)
    print(json.dumps({k: manifest[k] for k in ("frame_rate", "timeline_frames", "labels")}, indent=2))


if __name__ == "__main__":
    main()
