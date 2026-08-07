#!/usr/bin/env python3
"""Convert RGBA PNG images to paletted PlayStation TIM files (4/8 bpp)."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path
from PIL import Image


def psx_color(r: int, g: int, b: int, a: int) -> int:
    if a < 128:
        return 0
    value = (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)
    if a < 255:
        value |= 0x8000
    return value


def quantize_rgba(image: Image.Image, colors: int) -> tuple[list[int], bytes]:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    opaque = Image.new("RGB", rgba.size, (0, 0, 0))
    opaque.paste(rgba.convert("RGB"), mask=alpha)
    q = opaque.quantize(colors=colors - 1, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    source_palette = q.getpalette() or []
    palette = [0]
    for i in range(colors - 1):
        base = i * 3
        rgb = (source_palette[base:base + 3] + [0, 0, 0])[:3]
        palette.append(psx_color(rgb[0], rgb[1], rgb[2], 255))
    qdata = bytes((idx + 1 if a >= 128 else 0) for idx, a in zip(q.tobytes(), alpha.tobytes()))
    return palette, qdata


def encode_tim(image: Image.Image, bpp: int, vram_x: int = 0, vram_y: int = 0,
               clut_x: int = 0, clut_y: int = 0) -> bytes:
    if bpp not in (4, 8):
        raise ValueError("bpp must be 4 or 8")
    width, height = image.size
    pixels_per_word = 4 if bpp == 4 else 2
    if width % pixels_per_word:
        raise ValueError(f"Width {width} must be divisible by {pixels_per_word} for {bpp}bpp TIM")
    colors = 16 if bpp == 4 else 256
    palette, indices = quantize_rgba(image, colors)
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
