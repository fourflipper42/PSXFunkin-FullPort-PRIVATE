#!/usr/bin/env python3
"""Build PSXFunkin-ready 128x128 character cells and 256x256 TIM pages.

Frames are sampled only from actual source frames. No tweening, reconstruction or
fallback artwork is performed.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from animateatlas_flatten import AnimateAtlas, leaf_bounds, render_leaves_fixed, safe_name
from png_to_tim import encode_tim, decode_tim


PROFILE_LABELS = {
    "bf": {
        "idle", "left normal", "down normal", "up normal", "right normal",
        "left miss", "down miss", "up miss", "right miss", "hey", "scared",
    },
    "gf": {
        "danceLeft", "danceRight",
        "left 1", "down 1", "up 1", "right 1",
        "left miss 1", "down miss 1", "up miss 1", "right miss 1",
    },
}


def evenly_sample(start: int, duration: int, count: int) -> list[int]:
    if duration <= count:
        return list(range(start, start + duration))
    if count == 1:
        return [start]
    return [start + round(i * (duration - 1) / (count - 1)) for i in range(count)]


def sample_count(name: str, duration: int) -> int:
    lower = name.lower()
    if "idle" in lower or "dance" in lower:
        return min(4, duration)
    if "hey" in lower or "scared" in lower:
        return min(3, duration)
    return min(2, duration)


def build(atlas_dir: Path, output: Path, name: str, bpp: int = 4,
          vram_x: int = 0, vram_y: int = 0,
          clut_x: int = 0, clut_y: int = 0,
          profile: str = "all",
          sample_counts: dict[str, int] | None = None) -> dict[str, Any]:
    atlas = AnimateAtlas(atlas_dir)
    all_labels = atlas.labels()
    allowed = PROFILE_LABELS.get(profile)
    labels = [label for label in all_labels if allowed is None or label["name"] in allowed]
    if allowed is not None:
        missing = sorted(allowed - {label["name"] for label in labels})
        if missing:
            raise ValueError(f"{profile} profile labels missing from source atlas: {missing}")
    selected: list[dict[str, Any]] = []
    for label in labels:
        count = sample_count(label["name"], label["duration"])
        if sample_counts is not None and label["name"] in sample_counts:
            count = min(sample_counts[label["name"]], label["duration"])
        for sequence_index, frame in enumerate(evenly_sample(
                label["start"], label["duration"], count)):
            selected.append({"label": label["name"], "source_frame": frame,
                             "sequence_index": sequence_index})

    all_bounds = []
    for item in selected:
        all_bounds.extend(leaf_bounds(leaf) for leaf in atlas.leaves_for_frame(item["source_frame"]))
    min_x = min(b[0] for b in all_bounds); min_y = min(b[1] for b in all_bounds)
    max_x = max(b[2] for b in all_bounds); max_y = max(b[3] for b in all_bounds)
    padding = 4
    scale = min((128 - padding * 2) / (max_x - min_x),
                (128 - padding * 2) / (max_y - min_y))
    x_pad = (128 - (max_x - min_x) * scale) / 2
    y_pad = (128 - (max_y - min_y) * scale) / 2
    world = (scale, 0.0, 0.0, scale, x_pad - min_x * scale, y_pad - min_y * scale)

    output.mkdir(parents=True, exist_ok=True)
    cells_dir = output / "cells"; pages_dir = output / "pages"
    cells_dir.mkdir(exist_ok=True); pages_dir.mkdir(exist_ok=True)
    cells: list[Image.Image] = []
    for index, item in enumerate(selected):
        cell = render_leaves_fixed(atlas.leaves_for_frame(item["source_frame"]), (128, 128), world)
        cell_path = cells_dir / f"{index:03d}_{safe_name(item['label'])}_{item['sequence_index']}.png"
        cell.save(cell_path, optimize=True)
        item.update({"index": index, "cell": str(cell_path.relative_to(output)),
                     "page": index // 4, "src": [(index % 2) * 128, ((index % 4) // 2) * 128, 128, 128],
                     "offset": [64, 120]})
        cells.append(cell)

    pages = []
    for page_index in range(math.ceil(len(cells) / 4)):
        page = Image.new("RGBA", (256, 256))
        for slot in range(4):
            idx = page_index * 4 + slot
            if idx >= len(cells): break
            page.alpha_composite(cells[idx], ((slot % 2) * 128, (slot // 2) * 128))
        png_path = pages_dir / f"{name}{page_index:02d}.png"
        tim_path = pages_dir / f"{name}{page_index:02d}.tim"
        page.save(png_path, optimize=True)
        tim_data = encode_tim(page, bpp, vram_x, vram_y, clut_x, clut_y)
        tim_path.write_bytes(tim_data)
        decoded = decode_tim(tim_data)
        if decoded.size != page.size:
            raise RuntimeError(f"TIM verification failed for {tim_path}")
        pages.append({"index": page_index, "png": str(png_path.relative_to(output)),
                      "tim": str(tim_path.relative_to(output)), "bytes": len(tim_data)})

    manifest = {
        "name": name, "source": str(atlas_dir), "source_frame_rate": atlas.frame_rate,
        "policy": "authentic-source-frames-only", "bpp": bpp,
        "cell_size": [128, 128], "page_size": [256, 256], "scale": scale,
        "vram": {"texture": [vram_x, vram_y], "clut": [clut_x, clut_y]},
        "profile": profile,
        "excluded_labels": [label["name"] for label in all_labels if label not in labels],
        "world_bounds": [min_x, min_y, max_x, max_y],
        "frames": selected, "pages": pages, "labels": labels,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    contact = Image.new("RGBA", (512, math.ceil(len(pages) / 2) * 280), (32, 32, 32, 255))
    draw = ImageDraw.Draw(contact)
    for i, page_info in enumerate(pages):
        decoded = decode_tim((output / page_info["tim"]).read_bytes())
        x, y = (i % 2) * 256, (i // 2) * 280
        contact.alpha_composite(decoded, (x, y))
        draw.text((x + 4, y + 258), Path(page_info["tim"]).name, fill="white")
    contact.save(output / "decoded_contact.png", optimize=True)
    return manifest


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("atlas", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--name", required=True)
    p.add_argument("--bpp", type=int, choices=(4, 8), default=4)
    p.add_argument("--vram-x", type=int, required=True)
    p.add_argument("--vram-y", type=int, required=True)
    p.add_argument("--clut-x", type=int, required=True)
    p.add_argument("--clut-y", type=int, required=True)
    p.add_argument("--profile", choices=("all", "bf", "gf"), default="all")
    args = p.parse_args()
    manifest = build(args.atlas, args.output, args.name, args.bpp,
                     args.vram_x, args.vram_y, args.clut_x, args.clut_y,
                     args.profile)
    print(json.dumps({"name": manifest["name"], "frames": len(manifest["frames"]),
                      "pages": len(manifest["pages"]), "scale": manifest["scale"]}, indent=2))


if __name__ == "__main__":
    main()
