#!/usr/bin/env python3
"""Build Character Select quality v5 assets from official FNF v0.8.4 art.

v5 keeps v4's native 320x240 quality, but separates the live scene into:
  * static 320x240 16bpp environment/background (v4 CSBG16.BIN),
  * animated 320x240 8bpp BF/GF-only frames (CSCHAR8.RLE),
  * animated 320x240 8bpp official foreground frames (CSFG8.RLE),
  * a resident 256x240 8bpp official UI atlas (CSUI8.BIN).

This fixes the remaining compositing problem without returning to low-resolution
4bpp scene flattening. All source artwork is from the official v0.8.4 assets.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image

from build_charselect_quality_v4 import (
    W, H, FRAME_COUNT,
    IDLE_COUNT, LOCKED_COUNT, CONFIRM_COUNT, DENY_COUNT,
    quantize_8bpp, pack_csq2, decode_csq2,
)

UI_W = 256
UI_H = 240
UI_CLUT_BYTES = 512
UI_PIXEL_BYTES = UI_W * UI_H
UI_RECORD_BYTES = UI_CLUT_BYTES + UI_PIXEL_BYTES

LOCK_COLORS = [
    (0x31, 0xF2, 0xA5), (0x20, 0xEC, 0xCD), (0x24, 0xD9, 0xE8),
    (0x20, 0xEC, 0xCD), (0x20, 0xC8, 0xD4), (0x20, 0x9B, 0xDD),
    (0x20, 0x9B, 0xDD), (0x23, 0x62, 0xC9), (0x24, 0x3F, 0xB9),
]

LOCK_RECTS = [
    (0, 0, 48, 48), (48, 0, 48, 48),
    (128, 0, 48, 48), (176, 0, 48, 48),
    (0, 48, 48, 48), (48, 48, 48, 48),
    (128, 48, 48, 48), (176, 48, 48, 48),
    (0, 96, 48, 48),
]
BF_ICON_RECT = (48, 96, 48, 48)
CURSOR_DARK_RECT = (0, 144, 64, 64)
CURSOR_LIGHT_RECT = (64, 144, 64, 64)
CURSOR_MAIN_RECT = (128, 144, 64, 64)
BF_NAMETAG_RECT = (0, 208, 128, 32)
LOCK_NAMETAG_RECT = (128, 208, 128, 32)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load_module(path: Path, name: str):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot import {path}')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def clean_builder_copy(path: Path) -> Path:
    """Strip v3's foreground tail from build_character_overlay in a temp copy."""
    text = path.read_text()
    foreground = '''    # Official foreground order: speakers and foreground/card pieces are above\n    # GF/player, not flattened underneath them in the environment bank.\n    paste_anim(scene, anims.get("charSelectSpeakers"), -10, 0, i, count)\n    paste_static(scene, root, "foregroundBlur.png", -125, 170)\n    for png_name, xml_name, x, y in (\n        ("dipshitBlur.png", "dipshitBlur.xml", 419, -65),\n        ("dipshitBacking.png", "dipshitBacking.xml", 423, -17),\n    ):\n        png = root / "images" / "charSelect" / png_name\n        xml = root / "images" / "charSelect" / xml_name\n        if png.is_file() and xml.is_file():\n            scene.alpha_composite(sparrow_frame(png, xml, i, count), (x, y))\n    paste_static(scene, root, "chooseDipshit.png", 426, -13)\n    return scene.crop((160, 0, 1120, 720)).resize((CHAR_W, CHAR_H), Image.Resampling.LANCZOS)'''
    clean = '''    # v5 keeps GF/player separate from official foreground/UI layers.\n    return scene.crop((160, 0, 1120, 720)).resize((CHAR_W, CHAR_H), Image.Resampling.LANCZOS)'''
    if text.count(foreground) != 1:
        raise RuntimeError(f'cannot isolate v5 character layer; foreground tail count={text.count(foreground)}')
    out = Path('/tmp/build_v084_charselect_v5_clean.py')
    out.write_text(text.replace(foreground, clean, 1))
    return out


def build_foreground_overlay(mod, root: Path, anims: dict, i: int, count: int) -> Image.Image:
    scene = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
    mod.paste_anim(scene, anims.get('charSelectSpeakers'), -10, 0, i, count)
    mod.paste_static(scene, root, 'foregroundBlur.png', -125, 170)
    for png_name, xml_name, x, y in (
        ('dipshitBlur.png', 'dipshitBlur.xml', 419, -65),
        ('dipshitBacking.png', 'dipshitBacking.xml', 423, -17),
    ):
        png = root / 'images' / 'charSelect' / png_name
        xml = root / 'images' / 'charSelect' / xml_name
        if png.is_file() and xml.is_file():
            scene.alpha_composite(mod.sparrow_frame(png, xml, i, count), (x, y))
    mod.paste_static(scene, root, 'chooseDipshit.png', 426, -13)
    return scene.crop((160, 0, 1120, 720)).resize((W, H), Image.Resampling.LANCZOS)


def alpha_crop(image: Image.Image) -> Image.Image:
    image = image.convert('RGBA')
    bbox = image.getchannel('A').getbbox()
    if bbox is None:
        return Image.new('RGBA', (1, 1), (0, 0, 0, 0))
    return image.crop(bbox)


def fit(image: Image.Image, size: tuple[int, int], *, scale: float = 0.92) -> Image.Image:
    image = alpha_crop(image)
    max_w = max(1, int(size[0] * scale))
    max_h = max(1, int(size[1] * scale))
    ratio = min(max_w / image.width, max_h / image.height)
    nw = max(1, round(image.width * ratio))
    nh = max(1, round(image.height * ratio))
    resized = image.resize((nw, nh), Image.Resampling.LANCZOS)
    out = Image.new('RGBA', size, (0, 0, 0, 0))
    out.alpha_composite(resized, ((size[0] - nw) // 2, (size[1] - nh) // 2))
    return out


def tint_keep_luma(image: Image.Image, tint: tuple[int, int, int]) -> Image.Image:
    image = image.convert('RGBA')
    out = Image.new('RGBA', image.size, (0, 0, 0, 0))
    src = image.load()
    dst = out.load()
    tr, tg, tb = tint
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = src[x, y]
            if a == 0:
                continue
            lum = (r * 54 + g * 183 + b * 19) >> 8
            if lum < 32:
                nr = ng = nb = lum
            elif lum > 232:
                nr = ng = nb = lum
            else:
                factor = (lum + 64) / 319.0
                nr = min(255, round(tr * factor))
                ng = min(255, round(tg * factor))
                nb = min(255, round(tb * factor))
            dst[x, y] = (nr, ng, nb, a)
    return out


def tint_flat(image: Image.Image, tint: tuple[int, int, int]) -> Image.Image:
    image = image.convert('RGBA')
    alpha = image.getchannel('A')
    solid = Image.new('RGBA', image.size, (*tint, 255))
    solid.putalpha(alpha)
    return solid


def first_sparrow_frame(mod, root: Path, png_name: str, xml_name: str) -> Image.Image | None:
    png = root / 'images' / 'charSelect' / png_name
    xml = root / 'images' / 'charSelect' / xml_name
    if not (png.is_file() and xml.is_file()):
        return None
    try:
        return mod.sparrow_frame(png, xml, 0, 1)
    except Exception:
        return None


def load_static(root: Path, name: str) -> Image.Image | None:
    p = root / 'images' / 'charSelect' / name
    if not p.is_file():
        return None
    return Image.open(p).convert('RGBA')


def render_lock_source(mod, root: Path) -> Image.Image:
    for name in ('lock', 'locks'):
        try:
            anim = mod.load_optional_anim(root, name)
        except Exception:
            anim = None
        if anim is not None:
            canvas = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
            try:
                mod.paste_anim(canvas, anim, 0, 0, 0, 1)
                cropped = alpha_crop(canvas)
                if cropped.width > 1 and cropped.height > 1:
                    return cropped
            except Exception:
                pass
    fallback = first_sparrow_frame(mod, root, 'locks.png', 'locks.xml')
    if fallback is not None:
        return alpha_crop(fallback)
    raise RuntimeError('official Character Select lock artwork not found')


def render_icon(mod, root: Path) -> Image.Image:
    icon = first_sparrow_frame(mod, root, 'bfIcon.png', 'bfIcon.xml')
    if icon is None:
        icon = load_static(root, 'bfIcon.png')
    if icon is None:
        raise RuntimeError('official bfIcon artwork not found')
    return alpha_crop(icon)


def encode_ui8(image: Image.Image, psx_color) -> bytes:
    image = image.convert('RGBA')
    if image.size != (UI_W, UI_H):
        raise RuntimeError(f'UI atlas size {image.size} != {(UI_W, UI_H)}')
    alpha = image.getchannel('A')
    rgb = Image.new('RGB', image.size, (0, 0, 0))
    rgb.paste(image.convert('RGB'), mask=alpha)
    q = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw = q.getpalette()[:255 * 3]
    colors = [tuple(raw[i:i+3]) for i in range(0, len(raw), 3)]
    while len(colors) < 255:
        colors.append((0, 0, 0))
    import struct
    clut = b''.join(struct.pack('<H', c) for c in ([0] + [psx_color(c) for c in colors[:255]]))
    qpix = list(q.getdata())
    apix = list(alpha.getdata())
    pixels = bytes(0 if a < 128 else int(idx) + 1 for idx, a in zip(qpix, apix))
    result = clut + pixels
    if len(result) != UI_RECORD_BYTES:
        raise RuntimeError(f'UI atlas record {len(result)} != {UI_RECORD_BYTES}')
    return result


def paste_rect(atlas: Image.Image, image: Image.Image, rect: tuple[int, int, int, int]) -> None:
    x, y, w, h = rect
    fitted = fit(image, (w, h))
    atlas.alpha_composite(fitted, (x, y))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--builder', type=Path, required=True)
    ap.add_argument('--assets-root', type=Path, required=True)
    ap.add_argument('--upstream', type=Path, required=True)
    ap.add_argument('--report', type=Path, required=True)
    args = ap.parse_args()

    clean_path = clean_builder_copy(args.builder)
    mod = load_module(clean_path, 'charselect_v5_source')
    mod.SCENE_W = W
    mod.SCENE_H = H
    mod.CHAR_W = W
    mod.CHAR_H = H

    root = args.assets_root
    names = ['crowd', 'charSelectStage', 'barThing', 'bfChill', 'gfChill', 'lockedChill', 'charSelectSpeakers']
    anims = {name: mod.load_optional_anim(root, name) for name in names}
    for required in ('bfChill', 'lockedChill', 'charSelectSpeakers'):
        if anims.get(required) is None:
            raise RuntimeError(f'official Character Select animation missing: {required}')

    menu_dir = args.upstream / 'iso' / 'menu'
    modes = (
        [('idle', i, IDLE_COUNT) for i in range(IDLE_COUNT)] +
        [('locked', i, LOCKED_COUNT) for i in range(LOCKED_COUNT)] +
        [('confirm', i, CONFIRM_COUNT) for i in range(CONFIRM_COUNT)] +
        [('deny', i, DENY_COUNT) for i in range(DENY_COUNT)]
    )
    char_frames = [mod.build_character_overlay(root, anims, mode, i, count) for mode, i, count in modes]
    fg_frames = [build_foreground_overlay(mod, root, anims, i, count) for _mode, i, count in modes]

    char_records = [quantize_8bpp(frame, mod.base.psx_color) for frame in char_frames]
    fg_records = [quantize_8bpp(frame, mod.base.psx_color) for frame in fg_frames]
    if len(char_records) != FRAME_COUNT or len(fg_records) != FRAME_COUNT:
        raise RuntimeError('v5 live layer frame count mismatch')

    char_blob = pack_csq2(char_records)
    fg_blob = pack_csq2(fg_records)
    if decode_csq2(char_blob) != char_records:
        raise RuntimeError('v5 character CSQ2 round-trip failed')
    if decode_csq2(fg_blob) != fg_records:
        raise RuntimeError('v5 foreground CSQ2 round-trip failed')

    char_path = menu_dir / 'cschar8.rle'
    fg_path = menu_dir / 'csfg8.rle'
    char_path.write_bytes(char_blob)
    fg_path.write_bytes(fg_blob)
    if char_path.stat().st_size >= 500000 or fg_path.stat().st_size >= 500000:
        raise RuntimeError(f'v5 live bank unexpectedly large: char={char_path.stat().st_size} fg={fg_path.stat().st_size}')

    atlas = Image.new('RGBA', (UI_W, UI_H), (0, 0, 0, 0))
    lock = render_lock_source(mod, root)
    for i, rect in enumerate(LOCK_RECTS):
        paste_rect(atlas, tint_keep_luma(lock, LOCK_COLORS[i]), rect)
    paste_rect(atlas, render_icon(mod, root), BF_ICON_RECT)

    selector = load_static(root, 'charSelector.png')
    if selector is None:
        raise RuntimeError('official charSelector.png missing')
    paste_rect(atlas, tint_flat(selector, (0x3C, 0x74, 0xF7)), CURSOR_DARK_RECT)
    paste_rect(atlas, tint_flat(selector, (0x3E, 0xBB, 0xFF)), CURSOR_LIGHT_RECT)
    paste_rect(atlas, tint_flat(selector, (0xFF, 0xE0, 0x00)), CURSOR_MAIN_RECT)

    bf_name = load_static(root, 'boyfriendNametag.png')
    locked_name = load_static(root, 'lockedNametag.png')
    if bf_name is None or locked_name is None:
        raise RuntimeError('official Character Select nametag artwork missing')
    paste_rect(atlas, bf_name, BF_NAMETAG_RECT)
    paste_rect(atlas, locked_name, LOCK_NAMETAG_RECT)

    ui_path = menu_dir / 'csui8.bin'
    ui_path.write_bytes(encode_ui8(atlas, mod.base.psx_color))
    preview = args.report.parent / 'charselect_v5_ui_preview.png'
    atlas.save(preview)

    report = json.loads(args.report.read_text()) if args.report.is_file() else {}
    report['character_select_quality_v5'] = {
        'policy': 'separate native-resolution PS1 layers from official v0.8.4 assets',
        'character_layer': {
            'file': 'cschar8.rle', 'size': [W, H], 'format': 'PS1 8bpp per-frame CLUT',
            'frame_count': FRAME_COUNT, 'packed_bytes': char_path.stat().st_size, 'sha256': sha256(char_path),
            'content': 'BF/GF only; no speakers/foreground/title baked into this layer',
        },
        'foreground_layer': {
            'file': 'csfg8.rle', 'size': [W, H], 'format': 'PS1 8bpp per-frame CLUT',
            'frame_count': FRAME_COUNT, 'packed_bytes': fg_path.stat().st_size, 'sha256': sha256(fg_path),
            'content': 'speakers, foreground blur, CHOOSE backing/effects/title',
        },
        'ui_atlas': {
            'file': 'csui8.bin', 'size': [UI_W, UI_H], 'format': 'PS1 8bpp 256-color CLUT',
            'bytes': ui_path.stat().st_size, 'sha256': sha256(ui_path),
            'grid_origin_ps1': [97, 40], 'grid_spread_ps1': [36, 42],
            'nametag_midpoint_ps1': [283, 33],
            'official_lock_colors': ['#%02X%02X%02X' % c for c in LOCK_COLORS],
        },
    }
    args.report.write_text(json.dumps(report, indent=2) + '\n')

    print(f'v5 clean character bank: {char_path.stat().st_size} bytes')
    print(f'v5 separate foreground bank: {fg_path.stat().st_size} bytes')
    print(f'v5 HQ UI atlas: {ui_path.stat().st_size} bytes')
    print('v5 uses official 3x3 placement, per-slot lock colours, top-right native nametag, and independent foreground.')


if __name__ == '__main__':
    main()
