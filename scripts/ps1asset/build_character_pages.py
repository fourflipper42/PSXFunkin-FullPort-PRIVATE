#!/usr/bin/env python3
"""Build PSXFunkin-ready variable character frames and 256x256 TIM pages.

Frames are sampled only from actual source frames. No tweening, reconstruction or
fallback artwork is performed. Frames retain a common world transform, then are
cropped and shelf-packed with CuckyDev-style per-frame source rectangles/offsets.
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


def frame_bounds(atlas: AnimateAtlas, source_frame: int) -> tuple[float, float, float, float]:
    bounds = [leaf_bounds(leaf) for leaf in atlas.leaves_for_frame(source_frame)]
    if not bounds:
        raise ValueError(f"source frame {source_frame} contains no drawable leaves")
    return (min(row[0] for row in bounds), min(row[1] for row in bounds),
            max(row[2] for row in bounds), max(row[3] for row in bounds))


def reference_bounds(atlas: AnimateAtlas, selected: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    """Use normal idle/dance art for scale so special poses cannot shrink a character."""
    normal = [item for item in selected
              if "idle" in item["label"].lower() or "dance" in item["label"].lower()]
    if not normal:
        first_label = selected[0]["label"]
        normal = [item for item in selected if item["label"] == first_label]
    bounds = [frame_bounds(atlas, item["source_frame"]) for item in normal]
    return (min(row[0] for row in bounds), min(row[1] for row in bounds),
            max(row[2] for row in bounds), max(row[3] for row in bounds))


def pack_cells(cells: list[Image.Image]) -> tuple[list[Image.Image], list[tuple[int, int, int]]]:
    """Pack trimmed cells into 256px pages without changing their dimensions."""
    pages: list[Image.Image] = []
    shelves: list[list[dict[str, int]]] = []
    positions: list[tuple[int, int, int] | None] = [None] * len(cells)
    for index in sorted(range(len(cells)), key=lambda i: (cells[i].height, cells[i].width), reverse=True):
        width, height = cells[index].size
        if width > 256 or height > 256:
            raise ValueError(f"frame {index} is too large for a TIM page: {width}x{height}")
        placed = False
        for page_index, page_shelves in enumerate(shelves):
            for shelf in page_shelves:
                if height <= shelf["height"] and shelf["x"] + width <= 256:
                    x, y = shelf["x"], shelf["y"]
                    shelf["x"] += width
                    positions[index] = (page_index, x, y)
                    placed = True
                    break
            if placed:
                break
            y = sum(shelf["height"] for shelf in page_shelves)
            if y + height <= 256:
                page_shelves.append({"y": y, "height": height, "x": width})
                positions[index] = (page_index, 0, y)
                placed = True
                break
        if not placed:
            pages.append(Image.new("RGBA", (256, 256)))
            shelves.append([{"y": 0, "height": height, "x": width}])
            positions[index] = (len(pages) - 1, 0, 0)
    resolved = [position for position in positions if position is not None]
    if len(resolved) != len(cells):
        raise RuntimeError("internal frame packing failure")
    for index, (page_index, x, y) in enumerate(resolved):
        pages[page_index].alpha_composite(cells[index], (x, y))
    return pages, resolved


def build(atlas_dir: Path, output: Path, name: str, bpp: int = 4,
          vram_x: int = 0, vram_y: int = 0,
          clut_x: int = 0, clut_y: int = 0,
          profile: str = "all",
          sample_counts: dict[str, int] | None = None) -> dict[str, Any]:
    atlas = AnimateAtlas(atlas_dir)
    all_labels = atlas.labels()
    allowed = PROFILE_LABELS.get(profile)
    labels = [label for label in all_labels if allowed is None or label["name"] in allowed]
    if sample_counts is not None:
        requested = set(sample_counts)
        labels = [label for label in labels if label["name"] in requested]
        missing = sorted(requested - {label["name"] for label in labels})
        if missing:
            raise ValueError(f"requested labels missing from source atlas: {missing}")
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

    if not selected:
        raise ValueError(f"{atlas_dir}: no frames selected")
    min_x, min_y, max_x, max_y = reference_bounds(atlas, selected)
    reference_height = max_y - min_y
    if reference_height <= 0:
        raise ValueError(f"{atlas_dir}: invalid idle/dance reference bounds")
    target_height = 120
    scale = target_height / reference_height
    anchor_x, anchor_y = 128, 236
    center_x = (min_x + max_x) / 2
    world = (scale, 0.0, 0.0, scale,
             anchor_x - center_x * scale, anchor_y - max_y * scale)

    output.mkdir(parents=True, exist_ok=True)
    cells_dir = output / "cells"; pages_dir = output / "pages"
    cells_dir.mkdir(exist_ok=True); pages_dir.mkdir(exist_ok=True)
    cells: list[Image.Image] = []
    for index, item in enumerate(selected):
        bounds_world = frame_bounds(atlas, item["source_frame"])
        projected = (bounds_world[0] * scale + world[4], bounds_world[1] * scale + world[5],
                     bounds_world[2] * scale + world[4], bounds_world[3] * scale + world[5])
        overflow = projected[2] - projected[0] > 254 or projected[3] - projected[1] > 254
        # A few official attack poses bake a long projectile/effect into the
        # character frame. One PS1 TIM page cannot exceed 256px. Preserve the
        # character's body scale and clip only that peripheral overflow rather
        # than shrinking every frame because of one exceptional effect.
        shift_x = 0.0 if projected[2] - projected[0] > 254 else \
            max(0.0, 1 - projected[0]) + min(0.0, 255 - projected[2])
        shift_y = 0.0 if projected[3] - projected[1] > 254 else \
            max(0.0, 1 - projected[1]) + min(0.0, 255 - projected[3])
        frame_world = (world[0], world[1], world[2], world[3],
                       world[4] + shift_x, world[5] + shift_y)
        canvas = render_leaves_fixed(atlas.leaves_for_frame(item["source_frame"]),
                                     (256, 256), frame_world)
        alpha = canvas.getchannel("A").point(lambda value: 255 if value >= 8 else 0)
        bounds = alpha.getbbox()
        if bounds is None:
            raise ValueError(f"{atlas_dir}: selected frame {item['source_frame']} rendered empty")
        left, top, right, bottom = bounds
        left = max(0, left - 1); top = max(0, top - 1)
        right = min(256, right + 1); bottom = min(256, bottom + 1)
        cell = canvas.crop((left, top, right, bottom))
        cell.putalpha(cell.getchannel("A").point(lambda value: 255 if value >= 64 else 0))
        cell_path = cells_dir / f"{index:03d}_{safe_name(item['label'])}_{item['sequence_index']}.png"
        cell.save(cell_path, optimize=True)
        item.update({"index": index, "cell": str(cell_path.relative_to(output)),
                     "offset": [round(anchor_x + shift_x - left),
                                round(anchor_y + shift_y - top)],
                     "page_overflow_clipped": overflow})
        cells.append(cell)

    page_images, positions = pack_cells(cells)
    for item, cell, (page_index, x, y) in zip(selected, cells, positions):
        item.update({"page": page_index, "src": [x, y, cell.width, cell.height]})

    pages = []
    for page_index, page in enumerate(page_images):
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
        "frame_layout": "variable-rect-cuckydev-style", "page_size": [256, 256], "scale": scale,
        "vram": {"texture": [vram_x, vram_y], "clut": [clut_x, clut_y]},
        "profile": profile,
        "excluded_labels": [label["name"] for label in all_labels if label not in labels],
        "reference_bounds": [min_x, min_y, max_x, max_y],
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
