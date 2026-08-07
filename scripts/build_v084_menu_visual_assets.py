#!/usr/bin/env python3
"""Convert ONLY existing official FNF v0.8.4 menu art into PS1 TIM textures.

No artwork is drawn or synthesized here. The script performs technical porting
operations only: crop existing atlas frames, resize authentic source art, pack
it into VRAM atlases, palette-quantize, and encode PlayStation TIM files.
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

TRANSPARENT = (0, 0, 0, 0)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_tim_template(path: Path) -> dict[str, int]:
    data = path.read_bytes()
    if len(data) < 20 or struct.unpack_from("<I", data, 0)[0] != 0x10:
        raise ValueError(f"not a TIM: {path}")
    flags = struct.unpack_from("<I", data, 4)[0]
    mode = flags & 0x7
    if mode != 0 or not (flags & 0x8):
        raise ValueError(f"expected 4bpp CLUT TIM template: {path} flags={flags:#x}")
    off = 8
    clut_size = struct.unpack_from("<I", data, off)[0]
    cx, cy, cw, ch = struct.unpack_from("<4H", data, off + 4)
    off += clut_size
    image_size = struct.unpack_from("<I", data, off)[0]
    px, py, pw_words, ph = struct.unpack_from("<4H", data, off + 4)
    return {
        "clut_x": cx, "clut_y": cy, "clut_w": cw, "clut_h": ch,
        "px": px, "py": py, "pw_words": pw_words, "ph": ph,
        "width": pw_words * 4, "height": ph,
        "image_size": image_size,
    }


def psx_color(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    value = (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)
    # TIM color zero is transparent. Preserve opaque black as non-zero black.
    return 0x8000 if value == 0 else value


def encode_tim4(image: Image.Image, template: dict[str, int], out: Path) -> None:
    image = image.convert("RGBA")
    if image.size != (template["width"], template["height"]):
        raise ValueError(f"atlas {image.size} does not match template {(template['width'], template['height'])}")
    if image.width % 4:
        raise ValueError("4bpp TIM width must be divisible by four")

    alpha = image.getchannel("A")
    # Quantize the authentic pixels only; transparent technical padding is black.
    rgb = Image.new("RGB", image.size, (0, 0, 0))
    rgb.paste(image.convert("RGB"), mask=alpha)
    q = rgb.quantize(colors=15, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
    pal = q.getpalette()[:45]
    colors = [tuple(pal[i:i+3]) for i in range(0, len(pal), 3)]
    while len(colors) < 15:
        colors.append((0, 0, 0))

    qpix = list(q.getdata())
    apix = list(alpha.getdata())
    indices = [0 if a < 128 else (int(idx) + 1) for idx, a in zip(qpix, apix)]

    packed = bytearray()
    for y in range(image.height):
        row = indices[y * image.width:(y + 1) * image.width]
        for x in range(0, image.width, 4):
            word = row[x] | (row[x+1] << 4) | (row[x+2] << 8) | (row[x+3] << 12)
            packed += struct.pack("<H", word)

    clut = [0] + [psx_color(c) for c in colors]
    clut_data = b"".join(struct.pack("<H", c) for c in clut)
    clut_block = struct.pack(
        "<I4H", 12 + len(clut_data),
        template["clut_x"], template["clut_y"], 16, 1,
    ) + clut_data
    image_block = struct.pack(
        "<I4H", 12 + len(packed),
        template["px"], template["py"], image.width // 4, image.height,
    ) + packed
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(struct.pack("<II", 0x10, 0x08) + clut_block + image_block)


def trim(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    bbox = im.getchannel("A").getbbox()
    return im.crop(bbox) if bbox else im


def fit(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    im = trim(im)
    if im.width <= 0 or im.height <= 0:
        return Image.new("RGBA", size, TRANSPARENT)
    scale = min(size[0] / im.width, size[1] / im.height)
    nw = max(1, int(round(im.width * scale)))
    nh = max(1, int(round(im.height * scale)))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, TRANSPARENT)
    canvas.alpha_composite(im, ((size[0] - nw) // 2, (size[1] - nh) // 2))
    return canvas


def crop_4_3(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    target = 4 / 3
    ratio = im.width / im.height
    if ratio > target:
        nw = int(round(im.height * target))
        left = (im.width - nw) // 2
        return im.crop((left, 0, left + nw, im.height))
    nh = int(round(im.width / target))
    top = (im.height - nh) // 2
    return im.crop((0, top, im.width, top + nh))


def first_xml_frame(png: Path, xml: Path) -> Image.Image:
    im = Image.open(png).convert("RGBA")
    root = ET.parse(xml).getroot()
    sub = root.find("SubTexture")
    if sub is None:
        sub = next(iter(root), None)
    if sub is None:
        return trim(im)
    x = int(float(sub.attrib.get("x", "0")))
    y = int(float(sub.attrib.get("y", "0")))
    w = int(float(sub.attrib.get("width", str(im.width))))
    h = int(float(sub.attrib.get("height", str(im.height))))
    return trim(im.crop((x, y, x + w, y + h)))


def paste_box(atlas: Image.Image, art: Image.Image, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    fitted = fit(art, (w, h))
    atlas.alpha_composite(fitted, (x, y))


def load(root: Path, rel: str) -> Image.Image:
    p = root / rel
    if not p.is_file():
        raise FileNotFoundError(p)
    return Image.open(p).convert("RGBA")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets-root", type=Path, required=True)
    ap.add_argument("--upstream", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    root = args.assets_root
    upstream = args.upstream
    out_dir = upstream / "iso" / "menu"

    templates = {
        "back": parse_tim_template(out_dir / "back.tim"),
        "title": parse_tim_template(out_dir / "title.tim"),
        "story": parse_tim_template(out_dir / "story.tim"),
        "ng": parse_tim_template(out_dir / "ng.tim"),
    }
    expected = {
        "back": (256, 256), "title": (256, 256),
        "story": (256, 128), "ng": (128, 128),
    }
    for key, size in expected.items():
        got = (templates[key]["width"], templates[key]["height"])
        if got != size:
            raise SystemExit(f"unexpected {key}.tim template dimensions: {got}, expected {size}")

    used_sources: set[str] = set()
    def src(rel: str) -> Image.Image:
        used_sources.add(rel)
        return load(root, rel)
    def frame(png_rel: str, xml_rel: str) -> Image.Image:
        used_sources.add(png_rel); used_sources.add(xml_rel)
        return first_xml_frame(root / png_rel, root / xml_rel)

    # FREEPLAY: exact BF style background from data/ui/freeplay/styles/bf.json.
    fpbg = Image.new("RGBA", expected["back"], TRANSPARENT)
    bg = crop_4_3(src("images/freeplay/freeplayBGweek1-bf.png")).resize((256, 192), Image.Resampling.LANCZOS)
    fpbg.alpha_composite(bg, (0, 0))

    fpchar = Image.new("RGBA", expected["title"], TRANSPARENT)
    paste_box(fpchar, src("images/charSelect/bfChill.png"), (0, 0, 128, 192))
    paste_box(fpchar, src("images/freeplay/albumRoll/volume1.png"), (144, 8, 96, 96))
    paste_box(fpchar, frame("images/charSelect/bfIcon.png", "images/charSelect/bfIcon.xml"), (144, 120, 72, 64))

    fpui = Image.new("RGBA", expected["story"], TRANSPARENT)
    capsule = frame(
        "images/freeplay/freeplayCapsule/capsule/freeplayCapsule.png",
        "images/freeplay/freeplayCapsule/capsule/freeplayCapsule.xml",
    )
    paste_box(fpui, capsule, (0, 0, 192, 36))
    selector = frame(
        "images/freeplay/freeplaySelector/freeplaySelector.png",
        "images/freeplay/freeplaySelector/freeplaySelector.xml",
    )
    paste_box(fpui, selector, (200, 0, 32, 32))
    paste_box(fpui, src("images/freeplay/freeplayeasy.png"), (0, 48, 64, 20))
    paste_box(fpui, src("images/freeplay/freeplaynormal.png"), (64, 48, 64, 20))
    paste_box(fpui, src("images/freeplay/freeplayhard.png"), (128, 48, 64, 20))
    paste_box(fpui, src("images/freeplay/freeplayerect.png"), (192, 48, 64, 20))
    nightmare = frame("images/freeplay/freeplaynightmare.png", "images/freeplay/freeplaynightmare.xml")
    paste_box(fpui, nightmare, (0, 72, 96, 24))
    paste_box(fpui, src("images/freeplay/highscore.png"), (96, 72, 80, 20))
    paste_box(fpui, src("images/freeplay/freeplayCapsule/difficultytext.png"), (176, 72, 80, 20))

    fpextra = Image.new("RGBA", expected["ng"], TRANSPARENT)
    paste_box(fpextra, src("images/freeplay/albumRoll/volume1.png"), (0, 0, 64, 64))
    paste_box(fpextra, frame("images/freeplay/icons/bfpixel.png", "images/freeplay/icons/bfpixel.xml"), (64, 0, 64, 64))
    paste_box(fpextra, src("images/freeplay/miniArrow.png"), (0, 72, 32, 32))
    paste_box(fpextra, src("images/freeplay/seperator.png"), (40, 72, 80, 24))

    # CHARACTER SELECT: all layers are existing official v0.8.4 CharSelect art.
    csbg = Image.new("RGBA", expected["back"], TRANSPARENT)
    bg = crop_4_3(src("images/charSelect/charSelectBG.png")).resize((256, 192), Image.Resampling.LANCZOS)
    csbg.alpha_composite(bg, (0, 0))

    cslayer = Image.new("RGBA", expected["title"], TRANSPARENT)
    paste_box(cslayer, src("images/charSelect/charSelectStage.png"), (0, 0, 256, 142))
    paste_box(cslayer, src("images/charSelect/curtains.png"), (0, 154, 256, 91))

    cschar = Image.new("RGBA", expected["story"], TRANSPARENT)
    paste_box(cschar, src("images/charSelect/bfChill.png"), (0, 0, 128, 128))
    paste_box(cschar, src("images/charSelect/picoChill.png"), (128, 0, 128, 128))

    csui = Image.new("RGBA", expected["ng"], TRANSPARENT)
    paste_box(csui, src("images/charSelect/chooseDipshit.png"), (0, 0, 32, 64))
    paste_box(csui, frame("images/charSelect/bfIcon.png", "images/charSelect/bfIcon.xml"), (36, 0, 40, 36))
    paste_box(csui, frame("images/charSelect/picoIcon.png", "images/charSelect/picoIcon.xml"), (78, 0, 48, 36))
    paste_box(csui, src("images/charSelect/boyfriendNametag.png"), (0, 68, 80, 26))
    paste_box(csui, src("images/charSelect/lockedNametag.png"), (80, 68, 48, 28))
    paste_box(csui, src("images/charSelect/charSelector.png"), (0, 98, 32, 28))
    paste_box(csui, frame("images/charSelect/locks.png", "images/charSelect/locks.xml"), (40, 98, 24, 24))

    outputs = [
        ("fpbg.tim", fpbg, "back"),
        ("fpchar.tim", fpchar, "title"),
        ("fpui.tim", fpui, "story"),
        ("fpextra.tim", fpextra, "ng"),
        ("csbg.tim", csbg, "back"),
        ("cslayer.tim", cslayer, "title"),
        ("cschar.tim", cschar, "story"),
        ("csui.tim", csui, "ng"),
    ]
    report: dict[str, object] = {
        "policy": "official-v0.8.4-existing-files-only; no generated artwork",
        "templates": templates,
        "outputs": {},
        "sources": {},
    }
    for name, atlas, template_key in outputs:
        path = out_dir / name
        encode_tim4(atlas, templates[template_key], path)
        report["outputs"][name] = {
            "template": template_key,
            "size": list(atlas.size),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    for rel in sorted(used_sources):
        p = root / rel
        report["sources"][rel] = {"sha256": sha256(p), "bytes": p.stat().st_size}

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
