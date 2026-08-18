#!/usr/bin/env python3
"""Convert source artwork into FNF PS2's compact T8+RGBA CLUT format.

The source stays pristine. Conversion happens only for the PS2 build. 256-color
RGBA palettes are a strong fit for FNF's flat illustrated art and use roughly
one quarter of RGBA32 texture VRAM while preserving smooth edge alpha.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from PIL import Image

MAGIC = b"FPTX"
VERSION = 1
FORMAT_T8 = 8
HEADER = struct.Struct("<4sHHIIIIII")


def quantize_rgba(image: Image.Image) -> tuple[bytes, bytes]:
    rgba = image.convert("RGBA")
    indexed = rgba.quantize(
        colors=256,
        method=Image.Quantize.FASTOCTREE,
        dither=Image.Dither.NONE,
    )
    indices = bytes(indexed.getdata())

    # Rebuild an RGBA palette from the actual source pixels assigned to each
    # quantized index. Pillow's P palette is RGB-centric; doing this ourselves
    # retains semi-transparent antialiased edges.
    sums = [[0, 0, 0, 0, 0] for _ in range(256)]
    for idx, (r, g, b, a) in zip(indices, rgba.getdata()):
        bucket = sums[idx]
        bucket[0] += r
        bucket[1] += g
        bucket[2] += b
        bucket[3] += a
        bucket[4] += 1

    palette: list[list[int]] = []
    for rsum, gsum, bsum, asum, count in sums:
        if count:
            r = rsum // count
            g = gsum // count
            b = bsum // count
            # GS alpha is 0..0x80, with 0x80 representing fully opaque.
            a = ((asum // count) * 128 + 127) // 255
        else:
            r = g = b = a = 0
        palette.append([r, g, b, a])

    # gsKit/GS CSM1 expects the middle 8-color blocks of each 32-color CLUT
    # group swapped. Match gsKit's own 8-bit PNG loader exactly.
    for i in range(256):
        if (i & 0x18) == 0x08:
            palette[i], palette[i + 8] = palette[i + 8], palette[i]

    clut = bytes(component for entry in palette for component in entry)
    return indices, clut


def convert_image(image: Image.Image, dst: Path, *, source_label: str = "<image>") -> tuple[int, int]:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid image dimensions: {width}x{height}")
    if width > 4096 or height > 4096:
        raise ValueError(f"texture is unreasonably large for PS2 conversion: {width}x{height}")

    pixels, clut = quantize_rgba(rgba)
    expected = width * height
    if len(pixels) != expected:
        raise RuntimeError(f"pixel size mismatch: got {len(pixels)}, expected {expected}")
    if len(clut) != 256 * 4:
        raise RuntimeError(f"CLUT size mismatch: {len(clut)}")

    header = HEADER.pack(
        MAGIC,
        VERSION,
        FORMAT_T8,
        width,
        height,
        len(pixels),
        len(clut),
        0,
        0,
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(header + pixels + clut)
    print(
        f"{source_label} -> {dst}: {width}x{height}, "
        f"{len(pixels) + len(clut):,} payload bytes"
    )
    return width, height


def convert(src: Path, dst: Path) -> tuple[int, int]:
    with Image.open(src) as image:
        return convert_image(image, dst, source_label=str(src))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    convert(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
