#!/usr/bin/env python3
"""Build the official-art Memory Card icon used by console Options v1."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


def find_source(root: Path) -> Path:
    candidates = (
        root / "assets/images/icons/icon-bf.png",
        root / "assets/images/icons/icon-face.png",
    )
    for path in candidates:
        if path.is_file():
            return path
    raise SystemExit("official Boyfriend health icon is missing")


def psx_color(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)


def format_bytes(name: str, values: bytes) -> str:
    rows = []
    for offset in range(0, len(values), 12):
        rows.append("\t" + ", ".join(f"0x{x:02X}" for x in values[offset : offset + 12]))
    return f"static const u8 {name}[{len(values)}] = {{\n" + ",\n".join(rows) + "\n};\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets-root", type=Path, required=True)
    parser.add_argument("--header", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    args = parser.parse_args()

    source = find_source(args.assets_root)
    image = Image.open(source).convert("RGBA")
    # Health icons ship as two horizontal states; the save icon uses the first.
    if image.width >= image.height * 2:
        image = image.crop((0, 0, image.width // 2, image.height))
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise SystemExit("official Boyfriend health icon is empty")
    image = image.crop(bbox)
    image.thumbnail((16, 16), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((16 - image.width) // 2, (16 - image.height) // 2))

    opaque = Image.new("RGB", (16, 16), (0, 0, 0))
    opaque.paste(canvas.convert("RGB"), mask=canvas.getchannel("A"))
    quantized = opaque.quantize(colors=15, method=Image.Quantize.MEDIANCUT)
    raw_palette = quantized.getpalette()[: 15 * 3]
    palette_rgb = [(0, 0, 0)]
    palette_rgb.extend(tuple(raw_palette[i : i + 3]) for i in range(0, len(raw_palette), 3))
    while len(palette_rgb) < 16:
        palette_rgb.append((0, 0, 0))

    alpha_values = list(canvas.getchannel("A").getdata())
    quantized_values = list(quantized.getdata())
    indices = [0 if a < 64 else q + 1 for a, q in zip(alpha_values, quantized_values)]

    palette = bytearray()
    for rgb in palette_rgb:
        value = psx_color(rgb)
        palette.extend((value & 0xFF, value >> 8))
    pixels = bytearray()
    for i in range(0, 256, 2):
        pixels.append(indices[i] | (indices[i + 1] << 4))

    args.header.parent.mkdir(parents=True, exist_ok=True)
    args.header.write_text(
        "#ifndef _SETTINGS_ICON_GENERATED_H\n"
        "#define _SETTINGS_ICON_GENERATED_H\n\n"
        "// Downsampled from the official v0.8.4 Boyfriend health icon.\n"
        + format_bytes("settings_icon_palette", bytes(palette))
        + "\n"
        + format_bytes("settings_icon_pixels", bytes(pixels))
        + "\n#endif\n"
    )

    preview = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    out = []
    for idx in indices:
        if idx == 0:
            out.append((0, 0, 0, 0))
        else:
            out.append((*palette_rgb[idx], 255))
    preview.putdata(out)
    args.validation.parent.mkdir(parents=True, exist_ok=True)
    preview.resize((160, 160), Image.Resampling.NEAREST).save(args.validation)

    report = {
        "policy": "official-v0.8.4-boyfriend-health-icon-only",
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "icon_dimensions": [16, 16],
        "palette_bytes": len(palette),
        "pixel_bytes": len(pixels),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
