#!/usr/bin/env python3
"""Convert a Sparrow PNG+XML atlas into paged PS2 runtime assets.

Desktop FNF atlases can be several thousand pixels across. The PS2 renderer
keeps every animation frame at source resolution but repacks frame rectangles
into <=1024x1024 T8 pages. FATL v2 stores the page index per frame, so runtime
VRAM streaming can bind only the page needed for the current draw.
"""

from __future__ import annotations

import argparse
import importlib.util
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

HEADER_V2 = struct.Struct("<4sHHIIHH")
RECORD = struct.Struct("<IHHHHhhHHHH")
MAGIC = b"FATL"
VERSION = 2
PAGE_DIM = 1024
PAGE_PAD = 1


def load_texture_converter():
    path = Path(__file__).with_name("convert_texture.py")
    spec = importlib.util.spec_from_file_location("convert_texture", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def as_int(node: ET.Element, key: str, default: int = 0) -> int:
    value = node.get(key)
    return default if value is None or value == "" else int(value)


def checked_u16(value: int, label: str) -> int:
    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"{label} out of range: {value}")
    return value


def checked_s16(value: int, label: str) -> int:
    if not -0x8000 <= value <= 0x7FFF:
        raise ValueError(f"{label} out of range: {value}")
    return value


def page_texture_path(output_stem: Path, page_index: int) -> Path:
    if page_index == 0:
        return output_stem.with_suffix(".FPTX")
    return output_stem.with_name(f"{output_stem.name}_P{page_index:03d}").with_suffix(".FPTX")


def paste_with_edge_padding(page: Image.Image, crop: Image.Image, x: int, y: int) -> None:
    """Paste at x+PAD/y+PAD and extrude one source edge pixel into the gutter."""
    pad = PAGE_PAD
    w, h = crop.size
    dx = x + pad
    dy = y + pad
    page.paste(crop, (dx, dy))
    if pad == 0:
        return

    page.paste(crop.crop((0, 0, 1, h)), (dx - 1, dy))
    page.paste(crop.crop((w - 1, 0, w, h)), (dx + w, dy))
    page.paste(crop.crop((0, 0, w, 1)), (dx, dy - 1))
    page.paste(crop.crop((0, h - 1, w, h)), (dx, dy + h))
    page.putpixel((dx - 1, dy - 1), crop.getpixel((0, 0)))
    page.putpixel((dx + w, dy - 1), crop.getpixel((w - 1, 0)))
    page.putpixel((dx - 1, dy + h), crop.getpixel((0, h - 1)))
    page.putpixel((dx + w, dy + h), crop.getpixel((w - 1, h - 1)))


def convert(png_path: Path, xml_path: Path, output_stem: Path) -> tuple[int, int]:
    texture_converter = load_texture_converter()
    root = ET.parse(xml_path).getroot()
    frames = list(root.findall(".//SubTexture"))
    if not frames:
        raise ValueError(f"no SubTexture entries in {xml_path}")
    if len(frames) > 0xFFFF:
        raise ValueError(f"too many frames: {len(frames)}")

    with Image.open(png_path) as source_image:
        source = source_image.convert("RGBA")
    source_w, source_h = source.size

    strings = bytearray()
    records = bytearray()
    pages: list[Image.Image] = []
    page_used: list[tuple[int, int]] = []

    page = Image.new("RGBA", (PAGE_DIM, PAGE_DIM), (0, 0, 0, 0))
    page_index = 0
    cursor_x = 0
    cursor_y = 0
    shelf_h = 0
    used_w = 1
    used_h = 1

    for frame_index, frame in enumerate(frames):
        name = frame.get("name")
        if not name:
            raise ValueError("SubTexture is missing name")
        encoded = name.encode("utf-8") + b"\0"
        name_offset = len(strings)
        strings.extend(encoded)

        src_x = as_int(frame, "x")
        src_y = as_int(frame, "y")
        src_w = as_int(frame, "width")
        src_h = as_int(frame, "height")
        if src_w <= 0 or src_h <= 0:
            raise ValueError(f"{name}: invalid frame size {src_w}x{src_h}")
        if src_x < 0 or src_y < 0 or src_x + src_w > source_w or src_y + src_h > source_h:
            raise ValueError(
                f"{name}: source rect {src_x},{src_y} {src_w}x{src_h} exceeds {source_w}x{source_h}"
            )

        pack_w = src_w + PAGE_PAD * 2
        pack_h = src_h + PAGE_PAD * 2
        if pack_w > PAGE_DIM or pack_h > PAGE_DIM:
            raise ValueError(
                f"{name}: individual frame {src_w}x{src_h} exceeds PS2 atlas page {PAGE_DIM}x{PAGE_DIM}"
            )

        if cursor_x + pack_w > PAGE_DIM:
            cursor_x = 0
            cursor_y += shelf_h
            shelf_h = 0

        if cursor_y + pack_h > PAGE_DIM:
            pages.append(page.crop((0, 0, max(1, used_w), max(1, used_h))))
            page_used.append((max(1, used_w), max(1, used_h)))
            page = Image.new("RGBA", (PAGE_DIM, PAGE_DIM), (0, 0, 0, 0))
            page_index += 1
            if page_index > 0xFFFF:
                raise ValueError("atlas requires too many texture pages")
            cursor_x = 0
            cursor_y = 0
            shelf_h = 0
            used_w = 1
            used_h = 1

        crop = source.crop((src_x, src_y, src_x + src_w, src_y + src_h))
        paste_with_edge_padding(page, crop, cursor_x, cursor_y)
        packed_x = cursor_x + PAGE_PAD
        packed_y = cursor_y + PAGE_PAD
        used_w = max(used_w, cursor_x + pack_w)
        used_h = max(used_h, cursor_y + pack_h)
        shelf_h = max(shelf_h, pack_h)
        cursor_x += pack_w

        frame_x = checked_s16(as_int(frame, "frameX", 0), f"{name} frameX")
        frame_y = checked_s16(as_int(frame, "frameY", 0), f"{name} frameY")
        frame_w = checked_u16(as_int(frame, "frameWidth", src_w), f"{name} frameWidth")
        frame_h = checked_u16(as_int(frame, "frameHeight", src_h), f"{name} frameHeight")
        rotated = 1 if str(frame.get("rotated", "false")).lower() in ("true", "1") else 0

        records.extend(
            RECORD.pack(
                name_offset,
                checked_u16(packed_x, f"{name} x"),
                checked_u16(packed_y, f"{name} y"),
                checked_u16(src_w, f"{name} width"),
                checked_u16(src_h, f"{name} height"),
                frame_x,
                frame_y,
                frame_w,
                frame_h,
                rotated,
                page_index,
            )
        )

    pages.append(page.crop((0, 0, max(1, used_w), max(1, used_h))))
    page_used.append((max(1, used_w), max(1, used_h)))

    if len(pages) > 0xFFFF:
        raise ValueError(f"too many atlas pages: {len(pages)}")

    output_stem.parent.mkdir(parents=True, exist_ok=True)
    for index, page_image in enumerate(pages):
        dst = page_texture_path(output_stem, index)
        texture_converter.convert_image(
            page_image,
            dst,
            source_label=f"{png_path} [page {index + 1}/{len(pages)}]",
        )

    frames_path = output_stem.with_suffix(".FATL")
    header = HEADER_V2.pack(
        MAGIC,
        VERSION,
        len(frames),
        len(strings),
        RECORD.size,
        len(pages),
        0,
    )
    frames_path.write_bytes(header + records + strings)
    print(
        f"{xml_path} -> {frames_path}: {len(frames)} frames, "
        f"{len(pages)} page(s), source {source_w}x{source_h}"
    )
    return len(frames), len(pages)


def convert_frames(xml_path: Path, output_path: Path) -> int:
    """Legacy metadata-only helper retained for older tooling/tests.

    It writes FATL v2 with one page and unchanged source coordinates. New game
    conversion should use convert(), which repacks the texture and metadata as
    one atomic operation.
    """
    root = ET.parse(xml_path).getroot()
    frames = list(root.findall(".//SubTexture"))
    if not frames:
        raise ValueError(f"no SubTexture entries in {xml_path}")
    if len(frames) > 0xFFFF:
        raise ValueError(f"too many frames: {len(frames)}")

    strings = bytearray()
    records = bytearray()
    for frame in frames:
        name = frame.get("name")
        if not name:
            raise ValueError("SubTexture is missing name")
        name_offset = len(strings)
        strings.extend(name.encode("utf-8") + b"\0")
        w = checked_u16(as_int(frame, "width"), f"{name} width")
        h = checked_u16(as_int(frame, "height"), f"{name} height")
        records.extend(
            RECORD.pack(
                name_offset,
                checked_u16(as_int(frame, "x"), f"{name} x"),
                checked_u16(as_int(frame, "y"), f"{name} y"),
                w,
                h,
                checked_s16(as_int(frame, "frameX", 0), f"{name} frameX"),
                checked_s16(as_int(frame, "frameY", 0), f"{name} frameY"),
                checked_u16(as_int(frame, "frameWidth", w), f"{name} frameWidth"),
                checked_u16(as_int(frame, "frameHeight", h), f"{name} frameHeight"),
                1 if str(frame.get("rotated", "false")).lower() in ("true", "1") else 0,
                0,
            )
        )

    header = HEADER_V2.pack(MAGIC, VERSION, len(frames), len(strings), RECORD.size, 1, 0)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(header + records + strings)
    return len(frames)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("png", type=Path)
    parser.add_argument("xml", type=Path)
    parser.add_argument("output_stem", type=Path, help="Output path without extension")
    args = parser.parse_args()

    count, pages = convert(args.png, args.xml, args.output_stem)
    print(f"converted {count} frames across {pages} PS2 texture page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
