#!/usr/bin/env python3
"""Build the official-art Freeplay animation and metadata banks.

This is a technical conversion only. Every visible pixel comes from the
shipped Funkin v0.8.4 assets; the script crops atlas frames, scales them for
the PS1 framebuffer, palette-quantizes them, and writes TIM textures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

import build_v084_menu_visual_assets as base


ANIM_SIZE = (256, 256)
ANIM_VRAM = (448, 0)
ANIM_CLUT = (64, 481)
CAPSULE_SIZE = (104, 24)
SELECTOR_SIZE = (16, 30)
DIGIT_SIZE = (9, 14)
DIGIT_Y = 208
BPM_SIZE = (25, 14)
BPM_POS = (96, DIGIT_Y)

META_SIZE = (256, 256)
META_VRAM = (512, 0)
META_CLUT = (512, 480)
META_CELL = 48
META_COLUMN_X = (0, 48, 128, 176)
META_COLS = len(META_COLUMN_X)

ALBUMS = (
    "volume1",
    "volume2",
    "volume3",
    "volume4",
    "expansion1",
    "expansion2",
    "spaghetti",
)

ICONS = (
    "bfpixel",
    "dadpixel",
    "spookypixel",
    "monsterpixel",
    "picopixel",
    "mompixel",
    "parents-christmaspixel",
    "senpaipixel",
    "spiritpixel",
    "tankmanpixel",
    "gfpixel",
    "darnellpixel",
    "sserafim-kazuhapixel",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atlas_frames(png: Path, xml: Path, prefix: str) -> list[Image.Image]:
    source = Image.open(png).convert("RGBA")
    result: list[tuple[str, Image.Image]] = []
    for node in ET.parse(xml).getroot().findall("SubTexture"):
        name = node.attrib.get("name", "")
        if not name.startswith(prefix):
            continue
        x = int(float(node.attrib["x"]))
        y = int(float(node.attrib["y"]))
        w = int(float(node.attrib["width"]))
        h = int(float(node.attrib["height"]))
        fw = int(float(node.attrib.get("frameWidth", str(w))))
        fh = int(float(node.attrib.get("frameHeight", str(h))))
        fx = int(float(node.attrib.get("frameX", "0")))
        fy = int(float(node.attrib.get("frameY", "0")))
        frame = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
        frame.alpha_composite(source.crop((x, y, x + w, y + h)), (-fx, -fy))
        result.append((name, frame))
    result.sort(key=lambda item: item[0])
    if not result:
        raise RuntimeError(f"no frames beginning with {prefix!r} in {xml}")
    return [frame for _, frame in result]


def first_frame(png: Path, xml: Path) -> Image.Image:
    root = ET.parse(xml).getroot()
    node = root.find("SubTexture")
    if node is None:
        raise RuntimeError(f"no SubTexture in {xml}")
    return atlas_frames(png, xml, node.attrib.get("name", ""))[0]


def named_frame(png: Path, xml: Path, name: str) -> Image.Image:
    source = Image.open(png).convert("RGBA")
    for node in ET.parse(xml).getroot().findall("SubTexture"):
        if node.attrib.get("name") != name:
            continue
        x = int(float(node.attrib["x"]))
        y = int(float(node.attrib["y"]))
        w = int(float(node.attrib["width"]))
        h = int(float(node.attrib["height"]))
        return source.crop((x, y, x + w, y + h))
    raise RuntimeError(f"frame {name!r} missing from {xml}")


def palette_for(images: list[Image.Image], color_count: int) -> list[tuple[int, int, int]]:
    opaque: list[tuple[int, int, int]] = []
    for image in images:
        for red, green, blue, alpha in image.convert("RGBA").getdata():
            if alpha >= 128:
                opaque.append((red, green, blue))
    if not opaque:
        raise RuntimeError("cannot quantize an all-transparent image set")

    width = min(4096, len(opaque))
    height = math.ceil(len(opaque) / width)
    sample = Image.new("RGB", (width, height), opaque[-1])
    sample.putdata(opaque + [opaque[-1]] * (width * height - len(opaque)))
    quantized = sample.quantize(
        colors=color_count,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    raw = quantized.getpalette()[: color_count * 3]
    colors = [tuple(raw[i : i + 3]) for i in range(0, len(raw), 3)]
    while len(colors) < color_count:
        colors.append((0, 0, 0))
    return colors[:color_count]


def indexed(image: Image.Image, colors: list[tuple[int, int, int]]) -> list[int]:
    result: list[int] = []
    for red, green, blue, alpha in image.convert("RGBA").getdata():
        if alpha < 128:
            result.append(0)
            continue
        best = min(
            range(len(colors)),
            key=lambda index: (
                (red - colors[index][0]) ** 2
                + (green - colors[index][1]) ** 2
                + (blue - colors[index][2]) ** 2
            ),
        )
        result.append(best + 1)
    return result


def tim_clut(colors: list[tuple[int, int, int]], x: int, y: int) -> bytes:
    values = [0] + [base.psx_color(color) for color in colors]
    payload = b"".join(struct.pack("<H", value) for value in values)
    return struct.pack("<I4H", 12 + len(payload), x, y, len(values), 1) + payload


def write_tim4(image: Image.Image, path: Path, pixel_xy: tuple[int, int], clut_xy: tuple[int, int]) -> None:
    if image.size != ANIM_SIZE or image.width % 4:
        raise ValueError(f"unexpected 4bpp atlas dimensions: {image.size}")
    colors = palette_for([image], 15)
    pixels = indexed(image, colors)
    packed = bytearray()
    for y in range(image.height):
        row = pixels[y * image.width : (y + 1) * image.width]
        for x in range(0, image.width, 4):
            packed += struct.pack(
                "<H",
                row[x] | (row[x + 1] << 4) | (row[x + 2] << 8) | (row[x + 3] << 12),
            )
    image_block = struct.pack(
        "<I4H",
        12 + len(packed),
        pixel_xy[0],
        pixel_xy[1],
        image.width // 4,
        image.height,
    ) + packed
    path.write_bytes(struct.pack("<II", 0x10, 0x08) + tim_clut(colors, *clut_xy) + image_block)


def write_tim8(image: Image.Image, path: Path, pixel_xy: tuple[int, int], clut_xy: tuple[int, int]) -> None:
    if image.size != META_SIZE or image.width % 2:
        raise ValueError(f"unexpected 8bpp atlas dimensions: {image.size}")
    colors = palette_for([image], 255)
    packed = bytes(indexed(image, colors))
    image_block = struct.pack(
        "<I4H",
        12 + len(packed),
        pixel_xy[0],
        pixel_xy[1],
        image.width // 2,
        image.height,
    ) + packed
    path.write_bytes(struct.pack("<II", 0x10, 0x09) + tim_clut(colors, *clut_xy) + image_block)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets-root", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--validation-dir", type=Path)
    args = parser.parse_args()

    root = args.assets_root
    freeplay = root / "images/freeplay"
    output = args.upstream / "iso/menu"
    output.mkdir(parents=True, exist_ok=True)
    used: set[Path] = set()

    capsule_png = freeplay / "freeplayCapsule/capsule/freeplayCapsule.png"
    capsule_xml = freeplay / "freeplayCapsule/capsule/freeplayCapsule.xml"
    selector_png = freeplay / "freeplaySelector/freeplaySelector.png"
    selector_xml = freeplay / "freeplaySelector/freeplaySelector.xml"
    used.update((capsule_png, capsule_xml, selector_png, selector_xml))

    selected = atlas_frames(capsule_png, capsule_xml, "mp3 capsule w backing0")
    unselected = atlas_frames(capsule_png, capsule_xml, "mp3 capsule w backing NOT SELECTED")
    selectors = atlas_frames(selector_png, selector_xml, "arrow pointer loop")
    if len(selected) != 8 or len(unselected) != 8 or len(selectors) != 15:
        raise SystemExit(
            f"official animation frame counts changed: selected={len(selected)}, "
            f"unselected={len(unselected)}, selector={len(selectors)}"
        )

    anim = Image.new("RGBA", ANIM_SIZE, (0, 0, 0, 0))
    for index, frame in enumerate(selected):
        anim.alpha_composite(base.fit(frame, CAPSULE_SIZE), (0, index * CAPSULE_SIZE[1]))
    for index, frame in enumerate(unselected):
        anim.alpha_composite(base.fit(frame, CAPSULE_SIZE), (CAPSULE_SIZE[0], index * CAPSULE_SIZE[1]))
    for index, frame in enumerate(selectors):
        x = CAPSULE_SIZE[0] * 2 + (index % 3) * SELECTOR_SIZE[0]
        y = (index // 3) * SELECTOR_SIZE[1]
        anim.alpha_composite(base.fit(frame, SELECTOR_SIZE), (x, y))

    digit_png = freeplay / "freeplayCapsule/smallnumbers.png"
    digit_xml = freeplay / "freeplayCapsule/smallnumbers.xml"
    bpm_png = freeplay / "freeplayCapsule/bpmtext.png"
    used.update((digit_png, digit_xml, bpm_png))
    digit_names = ("ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE")
    for digit, name in enumerate(digit_names):
        frame = named_frame(digit_png, digit_xml, f"{name}0000")
        anim.alpha_composite(base.fit(frame, DIGIT_SIZE), (digit * DIGIT_SIZE[0], DIGIT_Y))
    anim.alpha_composite(base.fit(Image.open(bpm_png).convert("RGBA"), BPM_SIZE), BPM_POS)

    metadata = Image.new("RGBA", META_SIZE, (0, 0, 0, 0))
    metadata_entries: list[dict[str, object]] = []

    for name in ALBUMS:
        path = freeplay / f"albumRoll/{name}.png"
        used.add(path)
        metadata_entries.append({"kind": "album", "name": name, "image": Image.open(path).convert("RGBA")})
    for name in ICONS:
        png = freeplay / f"icons/{name}.png"
        xml = freeplay / f"icons/{name}.xml"
        used.update((png, xml))
        metadata_entries.append({"kind": "icon", "name": name, "image": first_frame(png, xml)})

    if len(metadata_entries) > META_COLS * (META_SIZE[1] // META_CELL):
        raise SystemExit("Freeplay metadata atlas overflow")
    report_entries: list[dict[str, object]] = []
    for index, entry in enumerate(metadata_entries):
        x = META_COLUMN_X[index % META_COLS]
        y = (index // META_COLS) * META_CELL
        metadata.alpha_composite(base.fit(entry.pop("image"), (META_CELL, META_CELL)), (x, y))
        report_entries.append({**entry, "index": index, "rect": [x, y, META_CELL, META_CELL]})

    anim_path = output / "fpanim.tim"
    meta_path = output / "fpmeta.tim"
    write_tim4(anim, anim_path, ANIM_VRAM, ANIM_CLUT)
    write_tim8(metadata, meta_path, META_VRAM, META_CLUT)
    if args.validation_dir is not None:
        args.validation_dir.mkdir(parents=True, exist_ok=True)
        anim.save(args.validation_dir / "freeplay-animation-atlas.png")
        metadata.save(args.validation_dir / "freeplay-metadata-atlas.png")

    report = {
        "policy": "official-v0.8.4-existing-files-only; crop/scale/palette conversion only",
        "animation": {
            "file": anim_path.name,
            "bytes": anim_path.stat().st_size,
            "sha256": sha256(anim_path),
            "vram": [*ANIM_VRAM, *ANIM_SIZE],
            "selected_capsules": 8,
            "unselected_capsules": 8,
            "selectors": 15,
            "capsule_cell": [*CAPSULE_SIZE],
            "selector_cell": [*SELECTOR_SIZE],
            "digit_cell": [0, DIGIT_Y, *DIGIT_SIZE],
            "bpm_rect": [*BPM_POS, *BPM_SIZE],
        },
        "metadata": {
            "file": meta_path.name,
            "bytes": meta_path.stat().st_size,
            "sha256": sha256(meta_path),
            "vram": [*META_VRAM, *META_SIZE],
            "cell": META_CELL,
            "entries": report_entries,
        },
        "sources": {
            str(path.relative_to(root)): {"bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in sorted(used)
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
