#!/usr/bin/env python3
"""Convert RGBA PNG images to paletted PlayStation TIM files (4/8 bpp)."""
from __future__ import annotations

import argparse
import struct
from collections import Counter
from pathlib import Path
from typing import Iterable
from PIL import Image


def psx_color(r: int, g: int, b: int, a: int) -> int:
    if a < 128:
        return 0
    # Match CuckyDev's converter: every opaque CLUT entry sets the high bit.
    # Without it, opaque RGB(0,0,0) becomes the PS1 transparent value and the
    # defining black Funkin outlines literally disappear.
    return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10) | 0x8000


def psx_rgb(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """Round once to the exact 5-bit colour precision stored by the PS1."""
    return tuple((channel >> 3) << 3 for channel in rgb)  # type: ignore[return-value]


def _select_palette(counts: Counter[tuple[int, int, int]], limit: int) -> list[tuple[int, int, int]]:
    """Choose opaque PS1 colours while protecting Base Funkin's dark inks."""
    if not counts:
        return []
    if len(counts) <= limit:
        palette_rgb = [rgb for rgb, _ in counts.most_common()]
    else:
        # Protect the most-used dark inks before reducing the remaining colours.
        # This keeps facial features and the heavy Base Funkin outline stable.
        dark = [(rgb, count) for rgb, count in counts.items()
                if (rgb[0] * 3 + rgb[1] * 6 + rgb[2]) // 10 <= 80]
        reserved = [rgb for rgb, _ in sorted(dark, key=lambda row: row[1], reverse=True)[:3]]
        remaining = []
        for rgb, count in counts.items():
            if rgb not in reserved:
                remaining.extend([rgb] * count)
        slots = max(1, limit - len(reserved))
        if remaining:
            width = min(256, len(remaining))
            height = (len(remaining) + width - 1) // width
            sample = Image.new("RGB", (width, height), remaining[-1])
            sample.putdata(remaining)
            quantized = sample.quantize(colors=slots, method=Image.Quantize.MEDIANCUT,
                                        dither=Image.Dither.NONE)
            raw_palette = quantized.getpalette() or []
            reduced = [psx_rgb(tuple(raw_palette[i:i + 3]))
                       for i in range(0, slots * 3, 3)]
        else:
            reduced = []
        palette_rgb = []
        for rgb in reserved + reduced:
            if rgb not in palette_rgb:
                palette_rgb.append(rgb)
        for rgb, _ in counts.most_common():
            if len(palette_rgb) >= limit:
                break
            if rgb not in palette_rgb:
                palette_rgb.append(rgb)

    return palette_rgb[:limit]


def build_palette_rgba(images: Iterable[Image.Image], colors: int) -> list[tuple[int, int, int]]:
    """Build one locked CLUT for a complete character or multi-page asset.

    Every source image contributes the same total weight. This prevents a large
    idle page from changing skin, clothing, or outline colours on rarer poses.
    """
    if colors not in (16, 256):
        raise ValueError("palette size must be 16 or 256")
    weighted: Counter[tuple[int, int, int]] = Counter()
    budget = 4096
    for image in images:
        local = Counter(
            psx_rgb((r, g, b))
            for r, g, b, a in image.convert("RGBA").getdata()
            if a >= 128
        )
        total = sum(local.values())
        if total == 0:
            continue
        for rgb, count in local.items():
            weighted[rgb] += max(1, round(count * budget / total))
    return _select_palette(weighted, colors - 1)


def quantize_rgba(image: Image.Image, colors: int,
                  palette_rgb: list[tuple[int, int, int]] | None = None) -> tuple[list[int], bytes]:
    rgba = image.convert("RGBA")
    pixels = list(rgba.getdata())
    opaque = [psx_rgb((r, g, b)) for r, g, b, a in pixels if a >= 128]
    limit = colors - 1
    if not opaque:
        return [0] * colors, bytes(len(pixels))

    if palette_rgb is None:
        palette_rgb = _select_palette(Counter(opaque), limit)
    else:
        palette_rgb = [psx_rgb(rgb) for rgb in palette_rgb[:limit]]
        if not palette_rgb:
            raise ValueError("locked palette cannot be empty for an opaque image")
    nearest_cache: dict[tuple[int, int, int], int] = {}
    def nearest(rgb: tuple[int, int, int]) -> int:
        if rgb not in nearest_cache:
            nearest_cache[rgb] = min(
                range(len(palette_rgb)),
                key=lambda i: (rgb[0] - palette_rgb[i][0]) ** 2
                              + (rgb[1] - palette_rgb[i][1]) ** 2
                              + (rgb[2] - palette_rgb[i][2]) ** 2,
            ) + 1
        return nearest_cache[rgb]

    indices = bytes(0 if a < 128 else nearest(psx_rgb((r, g, b)))
                    for r, g, b, a in pixels)
    palette = [0] + [psx_color(*rgb, 255) for rgb in palette_rgb]
    palette.extend([0] * (colors - len(palette)))
    return palette, indices


def encode_tim(image: Image.Image, bpp: int, vram_x: int = 0, vram_y: int = 0,
               clut_x: int = 0, clut_y: int = 0,
               palette_rgb: list[tuple[int, int, int]] | None = None) -> bytes:
    if bpp not in (4, 8):
        raise ValueError("bpp must be 4 or 8")
    width, height = image.size
    pixels_per_word = 4 if bpp == 4 else 2
    if width % pixels_per_word:
        raise ValueError(f"Width {width} must be divisible by {pixels_per_word} for {bpp}bpp TIM")
    colors = 16 if bpp == 4 else 256
    palette, indices = quantize_rgba(image, colors, palette_rgb)
    if bpp == 4:
        packed = bytearray()
        for i in range(0, len(indices), 2):
            packed.append(indices[i] | (indices[i + 1] << 4))
    else:
        packed = bytearray(indices)
    flags = 0x08 if bpp == 4 else 0x09
    clut_data = b"".join(struct.pack("<H", c) for c in palette)
    clut_block = struct.pack("<IHHHH", 12 + len(clut_data), clut_x, clut_y, colors, 1) + clut_data
    word_width = width // pixels_per_word
    image_block = struct.pack("<IHHHH", 12 + len(packed), vram_x, vram_y, word_width, height) + packed
    return struct.pack("<II", 0x10, flags) + clut_block + image_block


def decode_tim(data: bytes) -> Image.Image:
    magic, flags = struct.unpack_from("<II", data, 0)
    if magic != 0x10 or not flags & 0x08:
        raise ValueError("Only paletted TIM files are supported")
    bpp = 4 if (flags & 7) == 0 else 8
    offset = 8
    clut_size, _, _, colors, rows = struct.unpack_from("<IHHHH", data, offset)
    palette_raw = struct.unpack_from(f"<{colors * rows}H", data, offset + 12)
    offset += clut_size
    _, _, _, word_width, height = struct.unpack_from("<IHHHH", data, offset)
    raw = data[offset + 12:]
    width = word_width * (4 if bpp == 4 else 2)
    indices: list[int] = []
    if bpp == 4:
        for value in raw:
            indices.extend((value & 15, value >> 4))
    else:
        indices = list(raw)
    pixels = []
    for idx in indices[:width * height]:
        c = palette_raw[idx]
        if c == 0:
            pixels.append((0, 0, 0, 0))
        else:
            pixels.append(((c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3, 255))
    out = Image.new("RGBA", (width, height))
    out.putdata(pixels)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--bpp", type=int, choices=(4, 8), default=4)
    p.add_argument("--vram-x", type=int, default=0)
    p.add_argument("--vram-y", type=int, default=0)
    p.add_argument("--clut-x", type=int, default=0)
    p.add_argument("--clut-y", type=int, default=0)
    args = p.parse_args()
    image = Image.open(args.input).convert("RGBA")
    data = encode_tim(image, args.bpp, args.vram_x, args.vram_y, args.clut_x, args.clut_y)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(f"{args.output}: {image.width}x{image.height}, {args.bpp}bpp, {len(data)} bytes")


if __name__ == "__main__":
    main()
