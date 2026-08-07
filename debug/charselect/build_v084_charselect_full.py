#!/usr/bin/env python3
"""Build the v0.8.4 Character Select animation bank for PS1.

All raster content comes from the official v0.8.4 desktop assets. Animate
symbols are flattened at build time and the official introSelect video is
sampled into PS1-sized keyframes. Runtime only uploads tiny RAM-resident 4bpp
frames into the already-reserved Character Select background VRAM slot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image

import build_v084_menu_visual_assets as base

SCENE_W = 160
SCENE_H = 120
INTRO_COUNT = 24
IDLE_COUNT = 12
LOCKED_COUNT = 6
CONFIRM_COUNT = 8
DENY_COUNT = 4
INTRO_FIRST = 0
IDLE_FIRST = INTRO_FIRST + INTRO_COUNT
LOCKED_FIRST = IDLE_FIRST + IDLE_COUNT
CONFIRM_FIRST = LOCKED_FIRST + LOCKED_COUNT
DENY_FIRST = CONFIRM_FIRST + CONFIRM_COUNT
FRAME_COUNT = DENY_FIRST + DENY_COUNT
CLUT_BYTES = 16 * 2
PIXEL_BYTES = SCENE_W * SCENE_H // 2
RECORD_BYTES = CLUT_BYTES + PIXEL_BYTES

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def pack_4bpp(indices: list[int], width: int, height: int) -> bytes:
    if width % 4:
        raise ValueError("4bpp width must be divisible by four")
    if len(indices) != width * height:
        raise ValueError("index count mismatch")
    out = bytearray()
    for y in range(height):
        row = indices[y * width:(y + 1) * width]
        for x in range(0, width, 4):
            out += struct.pack("<H", row[x] | (row[x + 1] << 4) | (row[x + 2] << 8) | (row[x + 3] << 12))
    return bytes(out)


def quantize_frame(frame: Image.Image) -> tuple[list[int], list[tuple[int, int, int]]]:
    frame = frame.convert("RGBA")
    alpha = frame.getchannel("A")
    rgb = Image.new("RGB", frame.size, (0, 0, 0))
    rgb.paste(frame.convert("RGB"), mask=alpha)
    q = rgb.quantize(colors=15, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
    raw = q.getpalette()[:45]
    colors = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
    while len(colors) < 15:
        colors.append((0, 0, 0))
    qpix = list(q.getdata())
    apix = list(alpha.getdata())
    indices = [0 if a < 128 else int(i) + 1 for i, a in zip(qpix, apix)]
    return indices, colors[:15]


def frame_record(frame: Image.Image) -> bytes:
    indices, colors = quantize_frame(frame)
    clut = [0] + [base.psx_color(c) for c in colors]
    pal = b"".join(struct.pack("<H", c) for c in clut)
    pixels = pack_4bpp(indices, SCENE_W, SCENE_H)
    result = pal + pixels
    if len(result) != RECORD_BYTES:
        raise RuntimeError(f"Character Select frame record {len(result)} != {RECORD_BYTES}")
    return result


def mat_mul(a: Matrix, b: Matrix) -> Matrix:
    aa, ab, ac, ad, atx, aty = a
    ba, bb, bc, bd, btx, bty = b
    return (
        aa * ba + ac * bb,
        ab * ba + ad * bb,
        aa * bc + ac * bd,
        ab * bc + ad * bd,
        aa * btx + ac * bty + atx,
        ab * btx + ad * bty + aty,
    )


def point(m: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, tx, ty = m
    return a * x + c * y + tx, b * x + d * y + ty


def element_matrix(node: dict) -> Matrix:
    """Read Adobe Animate 2D MX or exported 4x4 M3D into our 2D affine tuple."""
    mx = node.get("MX")
    if isinstance(mx, list) and len(mx) >= 6:
        return tuple(float(v) for v in mx[:6])  # type: ignore[return-value]
    m3d = node.get("M3D")
    if isinstance(m3d, list) and len(m3d) >= 16:
        # Animate stores the affine basis/translation in a row-major 4x4 matrix.
        return (float(m3d[0]), float(m3d[1]), float(m3d[4]), float(m3d[5]),
                float(m3d[12]), float(m3d[13]))
    return IDENTITY


def symbol_duration(symbol: dict) -> int:
    return max(
        (int(fr.get("I", 0)) + int(fr.get("DU", 1))
         for layer in symbol.get("TL", {}).get("L", [])
         for fr in layer.get("FR", [])),
        default=1,
    )


def active_frame(layer: dict, frame_no: int) -> dict | None:
    for fr in layer.get("FR", []):
        start = int(fr.get("I", 0))
        if start <= frame_no < start + int(fr.get("DU", 1)):
            return fr
    return None


@dataclass
class SpriteRef:
    image: Image.Image
    x: int
    y: int
    w: int
    h: int
    rotated: bool = False


@dataclass
class AnimateAsset:
    folder: Path
    animation: dict
    symbols: dict[str, dict]
    sprites: dict[str, SpriteRef]
    root_symbol: str
    stage_matrix: Matrix = IDENTITY


def _strings(value) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _labels(symbol: dict) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for layer in symbol.get("TL", {}).get("L", []):
        for fr in layer.get("FR", []):
            for key in ("N", "L"):
                value = fr.get(key)
                if isinstance(value, str) and value:
                    result.append((int(fr.get("I", 0)), value))
    return sorted(set(result))


def choose_root(animation: dict, symbols: dict[str, dict], hint: str) -> str:
    an = animation.get("AN")
    if isinstance(an, dict):
        root_name = an.get("SN")
        if isinstance(root_name, str) and root_name in symbols:
            return root_name
    for candidate in _strings(an):
        if candidate in symbols:
            return candidate
    norm_hint = "".join(ch.lower() for ch in hint if ch.isalnum())
    for name in symbols:
        if "".join(ch.lower() for ch in name if ch.isalnum()) == norm_hint:
            return name
    scored: list[tuple[int, int, str]] = []
    for name, symbol in symbols.items():
        labs = " ".join(label.lower() for _, label in _labels(symbol))
        score = 0
        if "idle" in labs: score += 1000
        if "select" in labs: score += 500
        if hint.lower() in name.lower(): score += 250
        score += min(symbol_duration(symbol), 240)
        score += len(symbol.get("TL", {}).get("L", [])) * 2
        scored.append((score, symbol_duration(symbol), name))
    if not scored:
        raise RuntimeError(f"no symbols in {hint}")
    return max(scored)[2]


def load_animate(folder: Path) -> AnimateAsset:
    anim_path = folder / "Animation.json"
    if not anim_path.is_file():
        raise FileNotFoundError(anim_path)
    # Several shipped v0.8.4 Animate spritemaps include a UTF-8 BOM.
    animation = json.loads(anim_path.read_text(encoding="utf-8-sig"))
    sd = animation.get("SD")
    sd_symbols = sd.get("S", []) if isinstance(sd, dict) else []
    symbols = {s["SN"]: s for s in sd_symbols if isinstance(s, dict) and "SN" in s}
    # Some exported atlases (crowd/stage/speakers/etc.) store the root timeline
    # directly in AN and have no SD symbol dictionary. Keep that authoritative
    # root timeline in the same lookup table as normal symbols.
    an = animation.get("AN")
    if isinstance(an, dict) and isinstance(an.get("SN"), str) and isinstance(an.get("TL"), dict):
        symbols[str(an["SN"])] = an

    sprites: dict[str, SpriteRef] = {}
    for map_path in sorted(folder.glob("spritemap*.json")):
        png_path = map_path.with_suffix(".png")
        if not png_path.is_file():
            continue
        atlas = Image.open(png_path).convert("RGBA")
        data = json.loads(map_path.read_text(encoding="utf-8-sig"))
        atlas_data = data.get("ATLAS", {})
        entries = atlas_data.get("SPRITES", []) if isinstance(atlas_data, dict) else []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            sp = entry.get("SPRITE", {})
            if not isinstance(sp, dict):
                continue
            name = sp.get("name")
            if name is None:
                continue
            sprites[str(name)] = SpriteRef(
                atlas,
                int(sp.get("x", 0)), int(sp.get("y", 0)),
                int(sp.get("w", 0)), int(sp.get("h", 0)), bool(sp.get("rotated", False)),
            )
    if not sprites:
        raise RuntimeError(f"no Animate spritemap entries in {folder}")
    root_symbol = choose_root(animation, symbols, folder.name)
    stage_matrix = IDENTITY
    if isinstance(an, dict):
        sti = an.get("STI")
        if isinstance(sti, dict):
            si = sti.get("SI")
            if isinstance(si, dict):
                stage_matrix = element_matrix(si)
    return AnimateAsset(folder, animation, symbols, sprites, root_symbol, stage_matrix)


def collect_leaves(asset: AnimateAsset, symbol_name: str, frame_no: int,
                   parent: Matrix = IDENTITY, out=None, depth: int = 0):
    if out is None:
        out = []
    if depth > 32:
        raise RuntimeError(f"Animate recursion too deep in {asset.folder}")
    symbol = asset.symbols[symbol_name]
    duration = max(1, symbol_duration(symbol))
    frame_no %= duration
    for layer in reversed(symbol.get("TL", {}).get("L", [])):
        fr = active_frame(layer, frame_no)
        if fr is None:
            continue
        for element in reversed(fr.get("E", [])):
            if "ASI" in element:
                asi = element["ASI"]
                name = str(asi.get("N", ""))
                if name in asset.sprites:
                    mx = element_matrix(asi)
                    out.append((name, mat_mul(parent, mx)))
            elif "SI" in element:
                si = element["SI"]
                child = str(si.get("SN", ""))
                if child not in asset.symbols:
                    continue
                mx = element_matrix(si)
                first = int(si.get("FF", 0) or 0)
                child_frame = frame_no + first if si.get("ST", "G") == "G" else first
                collect_leaves(asset, child, child_frame, mat_mul(parent, mx), out, depth + 1)
    return out


def render_symbol(asset: AnimateAsset, frame_no: int, symbol_name: str | None = None) -> tuple[Image.Image, int, int]:
    symbol_name = symbol_name or asset.root_symbol
    leaves = collect_leaves(asset, symbol_name, frame_no, asset.stage_matrix)
    if not leaves:
        return Image.new("RGBA", (1, 1), base.TRANSPARENT), 0, 0
    bounds: list[tuple[float, float]] = []
    for name, matrix in leaves:
        sp = asset.sprites[name]
        for x, y in ((0, 0), (sp.w, 0), (0, sp.h), (sp.w, sp.h)):
            bounds.append(point(matrix, x, y))
    min_x = math.floor(min(x for x, _ in bounds)); min_y = math.floor(min(y for _, y in bounds))
    max_x = math.ceil(max(x for x, _ in bounds)); max_y = math.ceil(max(y for _, y in bounds))
    width, height = max(1, max_x - min_x), max(1, max_y - min_y)
    canvas = Image.new("RGBA", (width, height), base.TRANSPARENT)
    for name, matrix in leaves:
        sp = asset.sprites[name]
        crop = sp.image.crop((sp.x, sp.y, sp.x + sp.w, sp.y + sp.h))
        if sp.rotated:
            crop = crop.transpose(Image.Transpose.ROTATE_90)
        a, b, c, d, tx, ty = matrix
        det = a * d - b * c
        if abs(det) < 1e-9:
            continue
        ia, ic = d / det, -c / det
        ib, id_ = -b / det, a / det
        ox = ia * (min_x - tx) + ic * (min_y - ty)
        oy = ib * (min_x - tx) + id_ * (min_y - ty)
        warped = crop.transform((width, height), Image.Transform.AFFINE,
                                (ia, ic, ox, ib, id_, oy),
                                resample=Image.Resampling.BICUBIC)
        canvas.alpha_composite(warped)
    return canvas, min_x, min_y


def label_span(asset: AnimateAsset, label: str) -> tuple[int, int] | None:
    symbol = asset.symbols[asset.root_symbol]
    labels = _labels(symbol)
    wanted = label.lower().replace("_", " ")
    matches = [(pos, text) for pos, text in labels if wanted in text.lower().replace("_", " ")]
    if not matches:
        return None
    start = matches[0][0]
    later = sorted({pos for pos, _ in labels if pos > start})
    end = later[0] if later else symbol_duration(symbol)
    return start, max(start + 1, end)


def sample_frame(asset: AnimateAsset, seq_index: int, seq_count: int, label: str | None = None) -> int:
    span = label_span(asset, label) if label else None
    if span:
        start, end = span
        length = max(1, end - start)
        return start + min(length - 1, int((seq_index * length) / max(1, seq_count)))
    return seq_index % max(1, symbol_duration(asset.symbols[asset.root_symbol]))


def find_file(root: Path, name: str) -> Path:
    direct = root / "images" / "charSelect" / name
    if direct.is_file():
        return direct
    matches = [p for p in root.rglob(name) if p.is_file()]
    if not matches:
        raise FileNotFoundError(name)
    return matches[0]



def sparrow_frame(png: Path, xml: Path, seq_index: int, seq_count: int) -> Image.Image:
    atlas = Image.open(png).convert("RGBA")
    root = ET.parse(xml).getroot()
    nodes = list(root.findall(".//SubTexture"))
    if not nodes:
        raise RuntimeError(f"no SubTexture frames in {xml}")
    index = min(len(nodes) - 1, (seq_index * len(nodes)) // max(1, seq_count))
    node = nodes[index]
    x = int(float(node.attrib.get("x", 0)))
    y = int(float(node.attrib.get("y", 0)))
    w = int(float(node.attrib.get("width", 1)))
    h = int(float(node.attrib.get("height", 1)))
    crop = atlas.crop((x, y, x + w, y + h))
    fw = int(float(node.attrib.get("frameWidth", w)))
    fh = int(float(node.attrib.get("frameHeight", h)))
    fx = int(float(node.attrib.get("frameX", 0)))
    fy = int(float(node.attrib.get("frameY", 0)))
    if fw == w and fh == h and fx == 0 and fy == 0:
        return crop
    canvas = Image.new("RGBA", (max(1, fw), max(1, fh)), base.TRANSPARENT)
    canvas.alpha_composite(crop, (-fx, -fy))
    return canvas

def paste_static(scene: Image.Image, root: Path, rel: str, x: int, y: int) -> None:
    p = root / "images" / "charSelect" / rel
    if not p.is_file():
        return
    scene.alpha_composite(Image.open(p).convert("RGBA"), (x, y))


def paste_anim(scene: Image.Image, asset: AnimateAsset | None, x: int, y: int,
               seq_index: int, seq_count: int, label: str | None = None) -> None:
    if asset is None:
        return
    fr = sample_frame(asset, seq_index, seq_count, label)
    image, ox, oy = render_symbol(asset, fr)
    scene.alpha_composite(image, (x + ox, y + oy))


def crop_scene(scene: Image.Image) -> Image.Image:
    # The PC state is 1280x720; crop the central 960x720 view for PS1 4:3.
    return scene.crop((160, 0, 1120, 720)).resize((SCENE_W, SCENE_H), Image.Resampling.LANCZOS)


def load_optional_anim(root: Path, folder_name: str) -> AnimateAsset | None:
    folder = root / "images" / "charSelect" / folder_name
    try:
        return load_animate(folder)
    except (FileNotFoundError, RuntimeError):
        return None


def build_live_scene(root: Path, anims: dict[str, AnimateAsset | None], kind: str, i: int, count: int) -> Image.Image:
    scene = Image.new("RGBA", (1280, 720), (0, 0, 0, 255))
    paste_static(scene, root, "charSelectBG.png", -153, -140)
    paste_anim(scene, anims.get("crowd"), 0, 0, i, count)
    paste_anim(scene, anims.get("charSelectStage"), -2, 1, i, count)
    paste_static(scene, root, "curtains.png", -212, -99)
    paste_anim(scene, anims.get("barThing"), 0, 0, i, count)
    paste_static(scene, root, "charLight.png", 800, 250)
    paste_static(scene, root, "charLight.png", 180, 240)

    if kind in ("locked", "deny"):
        paste_anim(scene, anims.get("lockedChill"), 0, 0, i, count,
                   "cannot select Label" if kind == "deny" else "idle")
    else:
        gf_label = "confirm" if kind == "confirm" else "idle"
        bf_label = "select" if kind == "confirm" else "idle"
        paste_anim(scene, anims.get("gfChill"), 0, 0, i, count, gf_label)
        paste_anim(scene, anims.get("bfChill"), 0, 0, i, count, bf_label)

    paste_anim(scene, anims.get("charSelectSpeakers"), -10, 0, i, count)
    paste_static(scene, root, "foregroundBlur.png", -125, 170)

    # Authentic foreground choice card. Sparrow-atlas effects are represented by
    # their shipped first frame while the live stage/characters remain animated.
    for png_name, xml_name, x, y in (
        ("dipshitBlur.png", "dipshitBlur.xml", 419, -65),
        ("dipshitBacking.png", "dipshitBacking.xml", 423, -17),
    ):
        png = root / "images" / "charSelect" / png_name
        xml = root / "images" / "charSelect" / xml_name
        if png.is_file() and xml.is_file():
            scene.alpha_composite(sparrow_frame(png, xml, i, count), (x, y))
    paste_static(scene, root, "chooseDipshit.png", 426, -13)
    return crop_scene(scene)


def extract_intro_frames(video: Path, count: int) -> tuple[list[Image.Image], float]:
    if not video.is_file():
        raise FileNotFoundError(video)
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video)
    ], check=True, text=True, capture_output=True)
    duration = float(probe.stdout.strip())
    if duration <= 0:
        raise RuntimeError("introSelect video has invalid duration")
    result: list[Image.Image] = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for i in range(count):
            # Preserve the first and last visual beats while avoiding exact EOF.
            t = (duration * i / max(1, count - 1)) if i < count - 1 else max(0.0, duration - 0.03)
            out = td / f"intro-{i:02d}.png"
            subprocess.run([
                "ffmpeg", "-v", "error", "-y", "-ss", f"{t:.6f}", "-i", str(video),
                "-frames:v", "1", str(out)
            ], check=True)
            image = Image.open(out).convert("RGBA")
            result.append(base.crop_4_3(image).resize((SCENE_W, SCENE_H), Image.Resampling.LANCZOS))
    return result, duration


def write_first_frame_tim(path: Path, template: dict[str, int], frame: Image.Image) -> None:
    indices, colors = quantize_frame(frame)
    page = [0] * (template["width"] * template["height"])
    for y in range(SCENE_H):
        page[y * template["width"]:y * template["width"] + SCENE_W] = indices[y * SCENE_W:(y + 1) * SCENE_W]
    packed = pack_4bpp(page, template["width"], template["height"])
    clut = [0] + [base.psx_color(c) for c in colors]
    clut_data = b"".join(struct.pack("<H", c) for c in clut)
    clut_block = struct.pack("<I4H", 12 + len(clut_data), template["clut_x"], template["clut_y"], 16, 1) + clut_data
    image_block = struct.pack("<I4H", 12 + len(packed), template["px"], template["py"], template["pw_words"], template["ph"]) + packed
    path.write_bytes(struct.pack("<II", 0x10, 0x08) + clut_block + image_block)



def build_csui(root: Path, menu_dir: Path, report: dict) -> None:
    """Repack official Character Select foreground art for the live PS1 runtime."""
    template = base.parse_tim_template(menu_dir / "ng.tim")
    if (template["width"], template["height"]) != (128, 128):
        raise SystemExit("unexpected ng.tim template dimensions")

    cs = root / "images" / "charSelect"
    ui = Image.new("RGBA", (128, 128), base.TRANSPARENT)
    used: list[Path] = []

    def static(name: str) -> Image.Image:
        path = cs / name
        if not path.is_file():
            raise FileNotFoundError(path)
        used.append(path)
        return Image.open(path).convert("RGBA")

    def sparrow(png_name: str, xml_name: str, required: bool = True) -> Image.Image | None:
        png, xml = cs / png_name, cs / xml_name
        if not png.is_file() or not xml.is_file():
            if required:
                raise FileNotFoundError(f"missing official Sparrow source: {png} / {xml}")
            return None
        used.extend([png, xml])
        return base.first_xml_frame(png, xml)

    # Compact atlas. Every pixel comes from a shipped v0.8.4 source file.
    base.paste_box(ui, sparrow("bfIcon.png", "bfIcon.xml"), (0, 0, 40, 36))
    base.paste_box(ui, sparrow("picoIcon.png", "picoIcon.xml"), (40, 0, 48, 36))
    base.paste_box(ui, static("charSelector.png"), (92, 0, 32, 28))
    base.paste_box(ui, sparrow("locks.png", "locks.xml"), (0, 40, 24, 24))
    base.paste_box(ui, static("boyfriendNametag.png"), (24, 40, 80, 26))
    base.paste_box(ui, static("lockedNametag.png"), (0, 68, 48, 28))

    confirm = sparrow("charSelectorConfirm.png", "charSelectorConfirm.xml", required=False)
    denied = sparrow("charSelectorDenied.png", "charSelectorDenied.xml", required=False)
    if confirm is not None:
        base.paste_box(ui, confirm, (48, 68, 32, 28))
    else:
        base.paste_box(ui, static("charSelector.png"), (48, 68, 32, 28))
    if denied is not None:
        base.paste_box(ui, denied, (80, 68, 32, 28))
    else:
        base.paste_box(ui, static("charSelector.png"), (80, 68, 32, 28))

    out = menu_dir / "csui.tim"
    base.encode_tim4(ui, template, out)
    report.setdefault("outputs", {})["csui.tim"] = {
        "template": "ng", "size": [128, 128], "bytes": out.stat().st_size,
        "sha256": sha256(out),
        "content": "official BF/Pico icons, selector, lock, nametags, confirm and deny foreground art",
    }
    sources = report.setdefault("sources", {})
    for path in used:
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = str(path)
        sources[rel] = {"sha256": sha256(path), "bytes": path.stat().st_size}


def find_audio_stem(root: Path, stem: str) -> Path:
    wanted = stem.lower()
    exts = {".ogg", ".wav", ".mp3", ".flac"}
    matches = [p for p in root.rglob("*") if p.is_file() and p.stem.lower() == wanted and p.suffix.lower() in exts]
    if not matches:
        raise FileNotFoundError(f"official Character Select sound {stem}")
    return matches[0]


def build_sfx_bank(root: Path, psxavenc: Path, menu_dir: Path, src_dir: Path, intro_ticks: int) -> dict:
    names = [
        ("SELECT", "CS_select"),
        ("LOCKED", "CS_locked"),
        ("LIGHTS", "CS_Lights"),
        ("CONFIRM", "CS_confirm"),
    ]
    bank = bytearray()
    entries: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for macro, stem in names:
            source = find_audio_stem(root, stem)
            out = td / f"{macro.lower()}.snd"
            subprocess.run([str(psxavenc), "-t", "spu", "-f", "22050", str(source), str(out)], check=True)
            data = out.read_bytes()
            if not data or len(data) % 16:
                raise RuntimeError(f"{stem} SPU data is empty or not 16-byte ADPCM aligned")
            while len(bank) % 16:
                bank.append(0)
            offset = len(bank)
            bank.extend(data)
            entries[macro] = {
                "source": str(source.relative_to(root)),
                "source_sha256": sha256(source),
                "offset": offset,
                "bytes": len(data),
            }

    if len(bank) >= 0x30000:
        raise RuntimeError(f"Character Select SFX bank is too large for reserved SPU region: {len(bank)}")
    out_bank = menu_dir / "cssfx.bin"
    out_bank.write_bytes(bank)
    header = src_dir / "charselect_sfx_generated.h"
    lines = [
        "#ifndef _CHARSELECT_SFX_GENERATED_H",
        "#define _CHARSELECT_SFX_GENERATED_H",
        "",
        "#define MENU_CS_SFX_SPU_ADDR 0x10000",
        "#define MENU_CS_SFX_PITCH 0x0800",
        f"#define MENU_CS_SFX_BYTES {len(bank)}",
        f"#define MENU_CS_INTRO_TICKS {intro_ticks}",
    ]
    for macro, _ in names:
        lines.append(f"#define MENU_CS_SFX_{macro}_OFFSET {entries[macro]['offset']}")
    lines += ["", "#endif", ""]
    header.write_text("\n".join(lines))
    return {
        "file": "cssfx.bin",
        "sha256": sha256(out_bank),
        "bytes": len(bank),
        "sample_rate": 22050,
        "voice_pitch": "0x0800",
        "samples": entries,
    }

def build_stayfunky(root: Path, psxavenc: Path, out: Path) -> Path:
    candidates = [p for p in root.rglob("*") if p.is_file() and p.stem.lower() == "stayfunky" and p.suffix.lower() in {".ogg", ".wav", ".mp3", ".flac"}]
    if not candidates:
        raise FileNotFoundError("official stayFunky music")
    source = candidates[0]
    subprocess.run([str(psxavenc), "-t", "xa", "-f", "37800", "-b", "4", "-c", "2", str(source), str(out)], check=True)
    if out.stat().st_size == 0 or out.stat().st_size % 2336:
        raise RuntimeError("CHARSEL.XA is not a valid raw XA sector stream")
    return source


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets-root", type=Path, required=True)
    ap.add_argument("--upstream", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--intro-video", type=Path, required=True)
    ap.add_argument("--psxavenc", type=Path, required=True)
    args = ap.parse_args()

    root = args.assets_root
    csroot = root / "images" / "charSelect"
    if not csroot.is_dir():
        raise SystemExit(f"missing official Character Select directory: {csroot}")

    names = ["crowd", "charSelectStage", "barThing", "bfChill", "gfChill", "lockedChill", "charSelectSpeakers"]
    anims = {name: load_optional_anim(root, name) for name in names}
    required = ["crowd", "charSelectStage", "bfChill", "lockedChill", "charSelectSpeakers"]
    missing = [name for name in required if anims[name] is None]
    if missing:
        raise SystemExit(f"official Character Select Animate data missing: {missing}")

    frames: list[Image.Image] = []
    intro_frames, intro_duration = extract_intro_frames(args.intro_video, INTRO_COUNT)
    frames += intro_frames
    frames += [build_live_scene(root, anims, "idle", i, IDLE_COUNT) for i in range(IDLE_COUNT)]
    frames += [build_live_scene(root, anims, "locked", i, LOCKED_COUNT) for i in range(LOCKED_COUNT)]
    frames += [build_live_scene(root, anims, "confirm", i, CONFIRM_COUNT) for i in range(CONFIRM_COUNT)]
    frames += [build_live_scene(root, anims, "deny", i, DENY_COUNT) for i in range(DENY_COUNT)]
    if len(frames) != FRAME_COUNT:
        raise RuntimeError(f"built {len(frames)} frames, expected {FRAME_COUNT}")

    menu_dir = args.upstream / "iso" / "menu"
    menu_dir.mkdir(parents=True, exist_ok=True)
    template = base.parse_tim_template(menu_dir / "back.tim")
    if (template["width"], template["height"]) != (256, 256):
        raise SystemExit("unexpected back.tim template dimensions")

    stream = menu_dir / "csanim.bin"
    stream.write_bytes(b"".join(frame_record(frame) for frame in frames))
    if stream.stat().st_size != FRAME_COUNT * RECORD_BYTES:
        raise RuntimeError("Character Select stream size mismatch")

    csbg = menu_dir / "csbg.tim"
    write_first_frame_tim(csbg, template, frames[IDLE_FIRST])

    charsel_xa = args.upstream / "iso" / "music" / "charsel.xa"
    music_source = build_stayfunky(root, args.psxavenc, charsel_xa)
    intro_ticks = max(INTRO_COUNT, int(round(intro_duration * 60.0)))
    sfx_report = build_sfx_bank(root, args.psxavenc, menu_dir, args.upstream / "src", intro_ticks)

    report = json.loads(args.report.read_text()) if args.report.is_file() else {"outputs": {}, "sources": {}}
    build_csui(root, menu_dir, report)
    report["character_select_full"] = {
        "policy": "official v0.8.4 source/video only; no generated replacement artwork",
        "stream": {
            "file": "csanim.bin", "sha256": sha256(stream), "bytes": stream.stat().st_size,
            "frame_size": [SCENE_W, SCENE_H], "frame_count": FRAME_COUNT,
            "record_bytes": RECORD_BYTES,
            "ranges": {
                "intro": [INTRO_FIRST, INTRO_COUNT], "idle": [IDLE_FIRST, IDLE_COUNT],
                "locked": [LOCKED_FIRST, LOCKED_COUNT], "confirm": [CONFIRM_FIRST, CONFIRM_COUNT],
                "deny": [DENY_FIRST, DENY_COUNT],
            },
        },
        "intro_video": {"path": args.intro_video.name, "sha256": sha256(args.intro_video), "bytes": args.intro_video.stat().st_size, "duration_seconds": intro_duration, "runtime_ticks_60hz": intro_ticks},
        "music": {"source": str(music_source.relative_to(root)), "xa": "charsel.xa", "sha256": sha256(charsel_xa), "bytes": charsel_xa.stat().st_size},
        "sfx": sfx_report,
        "animate_roots": {name: (asset.root_symbol if asset else None) for name, asset in anims.items()},
    }
    report.setdefault("outputs", {})["csbg.tim"] = {
        "template": "back", "size": [256, 256], "bytes": csbg.stat().st_size,
        "sha256": sha256(csbg), "content": "Character Select live-frame upload target; first idle frame",
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n")

    print(f"Built Character Select: {FRAME_COUNT} frames x {SCENE_W}x{SCENE_H}, {stream.stat().st_size} bytes")
    print(f"Ranges intro={INTRO_FIRST}+{INTRO_COUNT} idle={IDLE_FIRST}+{IDLE_COUNT} locked={LOCKED_FIRST}+{LOCKED_COUNT} confirm={CONFIRM_FIRST}+{CONFIRM_COUNT} deny={DENY_FIRST}+{DENY_COUNT}")
    print(f"csanim.bin sha256={sha256(stream)}")
    print(f"charsel.xa sha256={sha256(charsel_xa)}")
    print(f"cssfx.bin bytes={sfx_report['bytes']} sha256={sfx_report['sha256']}")


if __name__ == "__main__":
    main()
