#!/usr/bin/env python3
"""Bake Adobe Animate / FlxAnimate texture-atlas characters into PS2 Sparrow pages.

Funkin's AnimateAtlas and MultiAnimateAtlas characters are hierarchical puppets:
Animation.json timelines reference nested symbols, which ultimately reference
spritemap limbs. Rendering that hierarchy on the PS2 EE every frame would be
needlessly expensive, so this tool resolves the timelines at build time and
flattens only the animation labels requested by character JSON.

The resulting synthetic Sparrow sheet keeps one union-sized logical frame for
all animations, with normal frameX/frameY trimming, then reuses the existing
paged FATL/FPTX converter. Runtime cost is therefore identical to Sparrow.
"""

from __future__ import annotations

import importlib.util
import io
import json
import math
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageEnhance, ImageFilter

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
SHEET_WIDTH = 4096
SHEET_PAD = 2


def load_sparrow_converter():
    path = Path(__file__).with_name("convert_sparrow_atlas.py")
    spec = importlib.util.spec_from_file_location("convert_sparrow_atlas_from_animate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def matrix(value=None) -> tuple[float, float, float, float, float, float]:
    raw = value or IDENTITY
    if len(raw) != 6:
        raise ValueError(f"Animate matrix must have six values: {raw!r}")
    return tuple(float(v) for v in raw)


def compose(child, parent):
    """Return parent(child(point)), matching FlxMatrix child.concat(parent)."""
    a, b, c, d, tx, ty = child
    A, B, C, D, TX, TY = parent
    return (
        A * a + C * b,
        B * a + D * b,
        A * c + C * d,
        B * c + D * d,
        A * tx + C * ty + TX,
        B * tx + D * ty + TY,
    )


def timeline_frame_count(timeline: dict) -> int:
    count = 0
    for layer in timeline.get("L") or []:
        for frame in layer.get("FR") or []:
            count = max(count, int(frame.get("I", 0)) + max(1, int(frame.get("DU", 1))))
    return count


def active_keyframe(layer: dict, index: int) -> dict | None:
    for frame in layer.get("FR") or []:
        start = int(frame.get("I", 0))
        duration = max(1, int(frame.get("DU", 1)))
        if start <= index < start + duration:
            return frame
    return None


def parse_color_transform(data: dict | None):
    if not data:
        return None
    mode = str(data.get("M") or "")
    if mode in ("AD", "Advanced"):
        return (
            [float(data.get(key, 1.0)) for key in ("RM", "GM", "BM", "AM")],
            [float(data.get(key, 0.0)) for key in ("RO", "GO", "BO", "AO")],
        )
    if mode in ("CA", "Alpha"):
        return ([1.0, 1.0, 1.0, float(data.get("AM", 1.0))], [0.0] * 4)
    if mode in ("CBRT", "Brightness"):
        brightness = float(data.get("BRT", 0.0))
        multiplier = 1.0 - abs(brightness)
        offset = brightness * 255.0 if brightness >= 0.0 else 0.0
        return ([multiplier, multiplier, multiplier, 1.0], [offset, offset, offset, 0.0])
    if mode in ("T", "Tint"):
        text = str(data.get("TC") or "#FFFFFF").lstrip("#")
        try:
            tint = [int(text[i:i + 2], 16) for i in (0, 2, 4)]
        except (ValueError, IndexError):
            tint = [255, 255, 255]
        amount = float(data.get("TM", 0.0))
        return (
            [1.0 - amount, 1.0 - amount, 1.0 - amount, 1.0],
            [tint[0] * amount, tint[1] * amount, tint[2] * amount, 0.0],
        )
    return None


def concat_color(parent, child):
    if child is None:
        return parent
    if parent is None:
        return child
    cm, co = child
    pm, po = parent
    # child first, then parent, matching ColorTransform.concat inheritance.
    return (
        [cm[i] * pm[i] for i in range(4)],
        [co[i] * pm[i] + po[i] for i in range(4)],
    )


def apply_color(image: Image.Image, transform) -> Image.Image:
    if transform is None:
        return image
    multipliers, offsets = transform
    channels = image.split()
    mapped = []
    for channel, mult, offset in zip(channels, multipliers, offsets):
        mapped.append(
            channel.point(
                lambda value, m=mult, o=offset: max(0, min(255, int(value * m + o + 0.5)))
            )
        )
    return Image.merge("RGBA", mapped)


def apply_filters(image: Image.Image, filters: Iterable[dict]) -> Image.Image:
    result = image
    for item in filters:
        name = str(item.get("N") or "")
        if name in ("BLF", "BlurFilter"):
            radius = max(float(item.get("BLX", 0.0)), float(item.get("BLY", 0.0))) * 0.5
            if radius > 0:
                result = result.filter(ImageFilter.GaussianBlur(radius=radius))
        elif name in ("ACF", "AdjustColorFilter"):
            brightness = float(item.get("BRT", 0.0))
            contrast = float(item.get("CT", 0.0))
            saturation = float(item.get("SAT", 0.0))
            hue = float(item.get("H", 0.0))
            if brightness:
                result = ImageEnhance.Brightness(result).enhance(max(0.0, 1.0 + brightness / 100.0))
            if contrast:
                result = ImageEnhance.Contrast(result).enhance(max(0.0, 1.0 + contrast / 100.0))
            if saturation:
                result = ImageEnhance.Color(result).enhance(max(0.0, 1.0 + saturation / 100.0))
            if hue:
                rgba = result
                rgb = rgba.convert("RGB").convert("HSV")
                h, s, v = rgb.split()
                shift = int((hue / 360.0) * 255.0)
                h = h.point(lambda value, off=shift: (value + off) & 0xFF)
                shifted = Image.merge("HSV", (h, s, v)).convert("RGB")
                shifted.putalpha(rgba.getchannel("A"))
                result = shifted
    return result


def load_spritemap_folder(folder: Path) -> dict[str, Image.Image]:
    sprites: dict[str, Image.Image] = {}
    json_files = sorted(folder.glob("spritemap*.json"))
    if not json_files:
        raise FileNotFoundError(f"no spritemap*.json under {folder}")

    for json_path in json_files:
        data = json.loads(json_path.read_text(encoding="utf-8-sig"))
        image_path = folder / str(data.get("meta", {}).get("image") or json_path.with_suffix(".png").name)
        if not image_path.exists():
            raise FileNotFoundError(image_path)
        with Image.open(image_path) as source_image:
            source = source_image.convert("RGBA")
        for wrapper in data.get("ATLAS", {}).get("SPRITES") or []:
            sprite = wrapper.get("SPRITE") or {}
            name = str(sprite.get("name") or "")
            if not name:
                continue
            x = int(sprite.get("x", 0))
            y = int(sprite.get("y", 0))
            w = int(sprite.get("w", 0))
            h = int(sprite.get("h", 0))
            if w <= 0 or h <= 0:
                continue
            if bool(sprite.get("rotated", False)):
                crop = source.crop((x, y, x + h, y + w)).transpose(Image.Transpose.ROTATE_270)
            else:
                crop = source.crop((x, y, x + w, y + h))
            sprites[name] = crop
    return sprites


def transformed_bounds(image: Image.Image, mx) -> tuple[float, float, float, float]:
    a, b, c, d, tx, ty = mx
    points = (
        (tx, ty),
        (a * image.width + tx, b * image.width + ty),
        (c * image.height + tx, d * image.height + ty),
        (a * image.width + c * image.height + tx, b * image.width + d * image.height + ty),
    )
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def collect_commands(animation: dict, sprites: dict[str, Image.Image], frame_index: int):
    symbols = {
        str(symbol.get("SN")): symbol.get("TL") or {}
        for symbol in animation.get("SD", {}).get("S") or []
        if symbol.get("SN")
    }
    commands: list[tuple[Image.Image, tuple, object, tuple[dict, ...]]] = []

    def walk(timeline: dict, index: int, parent_matrix, color_transform, filters, depth: int):
        if depth > 32:
            raise ValueError("Animate symbol recursion exceeds 32 levels")
        # FlxAnimate Timeline.draw() renders the layer array in reverse.
        for layer in reversed(timeline.get("L") or []):
            frame = active_keyframe(layer, index)
            if frame is None:
                continue
            relative = index - int(frame.get("I", 0))
            for element in frame.get("E") or []:
                atlas = element.get("ASI")
                if atlas is not None:
                    image = sprites.get(str(atlas.get("N")))
                    if image is not None:
                        commands.append(
                            (
                                image,
                                compose(matrix(atlas.get("MX")), parent_matrix),
                                color_transform,
                                tuple(filters),
                            )
                        )
                    continue

                instance = element.get("SI")
                if instance is None:
                    continue
                child = symbols.get(str(instance.get("SN")))
                if child is None:
                    continue
                child_count = timeline_frame_count(child)
                first = int(instance.get("FF", 0))
                loop = str(instance.get("LP") or "LP")
                if child_count <= 0:
                    child_index = 0
                elif loop in ("SF", "singleframe"):
                    child_index = min(max(first, 0), child_count - 1)
                elif loop in ("PO", "playonce"):
                    child_index = min(first + relative, child_count - 1)
                else:
                    child_index = (first + relative) % child_count
                child_color = concat_color(color_transform, parse_color_transform(instance.get("C")))
                child_filters = tuple(filters) + tuple(instance.get("F") or [])
                walk(
                    child,
                    child_index,
                    compose(matrix(instance.get("MX")), parent_matrix),
                    child_color,
                    child_filters,
                    depth + 1,
                )

    walk(animation.get("AN", {}).get("TL") or {}, frame_index, IDENTITY, None, (), 0)
    return commands


def paste_transformed(canvas: Image.Image, source: Image.Image, mx, transform, filters) -> None:
    source = apply_filters(apply_color(source, transform), filters)
    a, b, c, d, tx, ty = mx
    bounds = transformed_bounds(source, mx)
    min_x = math.floor(bounds[0]) - 3
    min_y = math.floor(bounds[1]) - 3
    max_x = math.ceil(bounds[2]) + 3
    max_y = math.ceil(bounds[3]) + 3
    if max_x <= min_x or max_y <= min_y:
        return
    determinant = a * d - b * c
    if abs(determinant) < 1e-8:
        return

    ia = d / determinant
    ib = -b / determinant
    ic = -c / determinant
    id_ = a / determinant
    coefficients = (
        ia,
        ic,
        -ia * tx - ic * ty + ia * min_x + ic * min_y,
        ib,
        id_,
        -ib * tx - id_ * ty + ib * min_x + id_ * min_y,
    )
    warped = source.transform(
        (max_x - min_x, max_y - min_y),
        Image.Transform.AFFINE,
        coefficients,
        resample=Image.Resampling.BICUBIC,
    )
    canvas.alpha_composite(warped, (min_x, min_y))


def label_ranges(animation: dict) -> dict[str, tuple[str, int, int]]:
    result: dict[str, tuple[str, int, int]] = {}
    for layer in animation.get("AN", {}).get("TL", {}).get("L") or []:
        for frame in layer.get("FR") or []:
            name = frame.get("N")
            if not name:
                continue
            original = str(name)
            result[original.lower()] = (
                original,
                int(frame.get("I", 0)),
                max(1, int(frame.get("DU", 1))),
            )
    return result


def build_synthetic_sheet(
    animation: dict,
    sprites: dict[str, Image.Image],
    prefixes: Iterable[str],
    png_path: Path,
    xml_path: Path,
) -> tuple[int, tuple[int, int]]:
    labels = label_ranges(animation)
    requested: list[tuple[str, int, int]] = []
    seen: set[str] = set()
    for prefix in prefixes:
        key = str(prefix).lower()
        if key in seen:
            continue
        seen.add(key)
        if key not in labels:
            raise ValueError(f"Animate label {prefix!r} not found")
        requested.append(labels[key])

    command_frames: list[tuple[str, int, list]] = []
    union = None
    for label, start, duration in requested:
        for local_index in range(duration):
            commands = collect_commands(animation, sprites, start + local_index)
            if not commands:
                continue
            command_frames.append((label, local_index, commands))
            for image, mx, _color, _filters in commands:
                bounds = transformed_bounds(image, mx)
                if union is None:
                    union = list(bounds)
                else:
                    union[0] = min(union[0], bounds[0])
                    union[1] = min(union[1], bounds[1])
                    union[2] = max(union[2], bounds[2])
                    union[3] = max(union[3], bounds[3])

    if not command_frames or union is None:
        raise ValueError("Animate conversion produced no visible frames")

    min_x = math.floor(union[0]) - 8
    min_y = math.floor(union[1]) - 8
    max_x = math.ceil(union[2]) + 8
    max_y = math.ceil(union[3]) + 8
    full_w = max_x - min_x
    full_h = max_y - min_y
    if full_w <= 0 or full_h <= 0 or full_w > 0xFFFF or full_h > 0xFFFF:
        raise ValueError(f"invalid Animate union bounds {full_w}x{full_h}")
    translate = (1.0, 0.0, 0.0, 1.0, -min_x, -min_y)

    rendered: list[tuple[str, Image.Image, tuple[int, int, int, int]]] = []
    for label, local_index, commands in command_frames:
        canvas = Image.new("RGBA", (full_w, full_h), (0, 0, 0, 0))
        for image, mx, color, filters in commands:
            paste_transformed(canvas, image, compose(mx, translate), color, filters)
        box = canvas.getbbox()
        if box is None:
            box = (0, 0, 1, 1)
            crop = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        else:
            crop = canvas.crop(box)
        rendered.append((f"{label}{local_index:04d}", crop, box))

    # Pack all trimmed frames into a temporary source sheet; the normal Sparrow
    # converter will repack them again into <=1024x1024 PS2 pages.
    positions: list[tuple[int, int]] = []
    cursor_x = SHEET_PAD
    cursor_y = SHEET_PAD
    shelf_h = 0
    sheet_h = SHEET_PAD
    for _name, image, _box in rendered:
        w, h = image.size
        if w + SHEET_PAD * 2 > SHEET_WIDTH:
            raise ValueError(f"baked Animate frame {w}x{h} exceeds synthetic sheet width")
        if cursor_x + w + SHEET_PAD > SHEET_WIDTH:
            cursor_x = SHEET_PAD
            cursor_y += shelf_h + SHEET_PAD
            shelf_h = 0
        positions.append((cursor_x, cursor_y))
        cursor_x += w + SHEET_PAD
        shelf_h = max(shelf_h, h)
        sheet_h = max(sheet_h, cursor_y + h + SHEET_PAD)

    sheet = Image.new("RGBA", (SHEET_WIDTH, sheet_h), (0, 0, 0, 0))
    root = ET.Element("TextureAtlas", {"imagePath": png_path.name})
    for (name, image, box), (x, y) in zip(rendered, positions):
        sheet.alpha_composite(image, (x, y))
        bx, by, _br, _bb = box
        ET.SubElement(
            root,
            "SubTexture",
            {
                "name": name,
                "x": str(x),
                "y": str(y),
                "width": str(image.width),
                "height": str(image.height),
                "frameX": str(-bx),
                "frameY": str(-by),
                "frameWidth": str(full_w),
                "frameHeight": str(full_h),
            },
        )

    png_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(png_path, optimize=True)
    ET.ElementTree(root).write(xml_path, encoding="utf-8", xml_declaration=True)
    return len(rendered), (full_w, full_h)


def convert(folder: Path, prefixes: Iterable[str], output_stem: Path) -> tuple[int, int, dict]:
    folder = folder.resolve()
    animation_path = folder / "Animation.json"
    if not animation_path.exists():
        raise FileNotFoundError(animation_path)
    animation = json.loads(animation_path.read_text(encoding="utf-8-sig"))
    sprites = load_spritemap_folder(folder)
    sparrow = load_sparrow_converter()

    with tempfile.TemporaryDirectory(prefix="fnf-ps2-animate-") as temp_name:
        temp = Path(temp_name)
        png_path = temp / "BAKED.png"
        xml_path = temp / "BAKED.xml"
        baked_frames, logical_size = build_synthetic_sheet(
            animation,
            sprites,
            prefixes,
            png_path,
            xml_path,
        )
        frame_count, page_count = sparrow.convert(png_path, xml_path, output_stem)

    metadata = {
        "source": folder.as_posix(),
        "bakedFrames": baked_frames,
        "logicalFrameWidth": logical_size[0],
        "logicalFrameHeight": logical_size[1],
        "pages": page_count,
        "frameRate": float(animation.get("MD", {}).get("FRT", 24)),
    }
    return frame_count, page_count, metadata


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("output_stem", type=Path)
    parser.add_argument("prefix", nargs="+")
    args = parser.parse_args()
    frames, pages, info = convert(args.folder, args.prefix, args.output_stem)
    print(json.dumps({"frames": frames, "pages": pages, **info}, indent=2))
