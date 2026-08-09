#!/usr/bin/env python3
"""Build Character Select v7 from the official v0.8.4 scene model.

v7 is intentionally structural rather than another placement hotfix:
- correct Adobe Animate display traversal (reverse layers, forward elements),
- animated native 320x240 8bpp environment frames,
- corrected BF/GF and foreground CSQ2 banks,
- one canonical official 3x3 grid transform,
- authored lock Sparrow frames rather than whole-image synthetic tinting,
- the actual Freeplay PixelatedIcon source (freeplay/icons/bfpixel),
- smaller PS1-adapted nametags,
- complete 320x240 PNG validation frames before PS1 compilation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from build_charselect_quality_v4 import (
    W, H, FRAME_COUNT, IDLE_COUNT, LOCKED_COUNT, CONFIRM_COUNT, DENY_COUNT,
    quantize_8bpp, pack_csq2, decode_csq2,
)
import build_charselect_quality_v5 as v5
import build_charselect_exact_ui_v6 as v6

SOURCE_W = 1280
SOURCE_H = 720
CROP_X = 160
CROP_W = 960
WORLD_SCALE = 1.0 / 3.0

GRID_X = 450
GRID_Y = 120
GRID_X_SPREAD = 107
GRID_Y_SPREAD = 127
BF_SLOT = 4
CURSOR_FACTOR = 110
CURSOR_OFFSET_X = -16
CURSOR_OFFSET_Y = -48

GRID_CLUT = (0, 509)
GRID_PAGES = ((768, 0, 128), (832, 0, 128), (960, 0, 64))
CTRL_CLUT = (0, 511)
CTRL_PAGES = ((448, 256, 128), (512, 256, 128))
CTRL_W = 256
CTRL_H = 240

BG_MAX_PACKED = 430_000
LIVE_BANK_BUDGET = 1_050_000


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def corrected_builder_copy(path: Path) -> Path:
    """Fix the display-list mistake, then strip the old foreground tail."""
    text = path.read_text()
    old = 'for element in reversed(fr.get("E", [])):'
    new = 'for element in fr.get("E", []):'
    if text.count(old) != 1:
        raise RuntimeError(f'Animate element-order anchor count={text.count(old)}')
    # Adobe Animate layer order stays reversed for back-to-front compositing;
    # elements within the active layer are already in back-to-front order.
    order_path = Path('/tmp/build_v084_charselect_v7_order.py')
    order_path.write_text(text.replace(old, new, 1))
    return v5.clean_builder_copy(order_path)


def load_builder(path: Path):
    return v5.load_module(path, 'charselect_v7_source')


def crop_alpha(image: Image.Image) -> Image.Image:
    image = image.convert('RGBA')
    bbox = image.getchannel('A').getbbox()
    if bbox is None:
        return Image.new('RGBA', (1, 1), (0, 0, 0, 0))
    return image.crop(bbox)


def ps1_crop(image: Image.Image) -> Image.Image:
    return image.convert('RGBA').crop((CROP_X, 0, CROP_X + CROP_W, SOURCE_H)).resize(
        (W, H), Image.Resampling.LANCZOS
    )


def traversal_rmse(mod, root: Path) -> float:
    ref = Image.open(root / 'images' / 'charSelect' / 'bfChill.png').convert('RGBA')
    asset = mod.load_animate(root / 'images' / 'charSelect' / 'bfChill')
    image, _ox, _oy = mod.render_symbol(asset, 0)
    a = crop_alpha(image)
    b = crop_alpha(ref)
    a = a.resize(b.size, Image.Resampling.LANCZOS)
    errs = []
    for bg in ((0, 0, 0, 255), (255, 255, 255, 255)):
        aa = Image.new('RGBA', b.size, bg); aa.alpha_composite(a)
        bb = Image.new('RGBA', b.size, bg); bb.alpha_composite(b)
        stat = ImageStat.Stat(ImageChops.difference(aa.convert('RGB'), bb.convert('RGB')))
        errs.append(math.sqrt(sum(v * v for v in stat.rms)))
    return sum(errs) / len(errs)


def build_bg_bank(mod, root: Path, anims: dict) -> tuple[int, list[Image.Image], bytes, list[bytes]]:
    """Use the largest genuine sampled background animation that fits RAM."""
    for count in (8, 6):
        frames = [mod.build_environment_scene(root, anims, i, count) for i in range(count)]
        records = [quantize_8bpp(frame, mod.base.psx_color) for frame in frames]
        blob = pack_csq2(records)
        unique = len({hashlib.sha256(r).digest() for r in records})
        if unique < min(3, count):
            raise RuntimeError(f'official environment sampling is effectively static: {unique}/{count}')
        if len(blob) <= BG_MAX_PACKED:
            if decode_csq2(blob) != records:
                raise RuntimeError('v7 background CSQ2 round-trip failed')
            return count, frames, blob, records
    raise RuntimeError('animated 320x240 background exceeds v7 safe RAM budget')


def build_foreground_overlay(mod, root: Path, anims: dict, i: int, count: int) -> Image.Image:
    scene = Image.new('RGBA', (SOURCE_W, SOURCE_H), (0, 0, 0, 0))
    # Official create() order puts speakers and card/blur pieces after GF/BF.
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
    return ps1_crop(scene)


def reconstruct_sparrow_frame(png: Path, node: ET.Element) -> Image.Image:
    atlas = Image.open(png).convert('RGBA')
    x = int(node.attrib.get('x', 0)); y = int(node.attrib.get('y', 0))
    w = int(node.attrib.get('width', 0)); h = int(node.attrib.get('height', 0))
    fw = int(node.attrib.get('frameWidth', w)); fh = int(node.attrib.get('frameHeight', h))
    fx = int(node.attrib.get('frameX', 0)); fy = int(node.attrib.get('frameY', 0))
    crop = atlas.crop((x, y, x + w, y + h))
    out = Image.new('RGBA', (fw, fh), (0, 0, 0, 0))
    out.alpha_composite(crop, (-fx, -fy))
    return out


def lock_frames(root: Path) -> list[Image.Image]:
    base = root / 'images' / 'charSelect'
    png = base / 'locks.png'; xml = base / 'locks.xml'
    if not (png.is_file() and xml.is_file()):
        raise RuntimeError('official locks.png/xml missing')
    nodes = list(ET.parse(xml).getroot())
    result = []
    color_signatures = []
    for variant in range(1, 10):
        prefix = f'LOCK FULL {variant} instance '
        matches = [n for n in nodes if n.attrib.get('name', '').startswith(prefix)]
        if not matches:
            raise RuntimeError(f'official lock variant {variant} missing from locks.xml')
        # Around frame 9 the authored lock has reached the full closed silhouette.
        def score(n: ET.Element):
            name = n.attrib.get('name', '')
            m = re.search(r'(\d+)$', name)
            number = int(m.group(1)) if m else 0
            return (abs(number - 10009), -(int(n.attrib.get('width', 0)) * int(n.attrib.get('height', 0))))
        node = min(matches, key=score)
        image = reconstruct_sparrow_frame(png, node)
        result.append(image)
        # Verify these are genuinely authored variants, not one monochrome image
        # that would force us back into the old incorrect whole-lock tint hack.
        rgba = image.convert('RGBA')
        pix = [(r, g, b) for r, g, b, a in rgba.getdata() if a > 128 and (r + g + b) > 80]
        if pix:
            color_signatures.append(tuple(sum(p[c] for p in pix) // len(pix) for c in range(3)))
        else:
            color_signatures.append((0, 0, 0))
    coarse = {tuple(v // 24 for v in sig) for sig in color_signatures}
    if len(coarse) < 4:
        raise RuntimeError(f'locks.xml variants do not preserve authored colors: {color_signatures}')
    return result


def build_grid(root: Path) -> tuple[Image.Image, list[list[int]]]:
    canvas = Image.new('RGBA', (SOURCE_W, SOURCE_H), (0, 0, 0, 0))
    locks = lock_frames(root)
    cells = []
    for index in range(9):
        col = index % 3; row = index // 3
        x = GRID_X + col * GRID_X_SPREAD
        y = GRID_Y + row * GRID_Y_SPREAD
        cells.append([x, y])
        if index == BF_SLOT:
            continue
        # Lock.hx's (230,110) offset compensates the Animate canvas internally.
        # The trimmed logical 122x133 Sparrow frame therefore belongs at the
        # member's actual grid x/y, not x+offset (the v6 placement error).
        canvas.alpha_composite(locks[index], (x, y))
    return ps1_crop(canvas), cells


def find_bf_pixel_icon(root: Path) -> tuple[Path, Path]:
    icons = root / 'images' / 'freeplay' / 'icons'
    if not icons.is_dir():
        raise RuntimeError('official freeplay icon directory missing')
    candidates = [p for p in icons.rglob('*.png') if p.stem.lower() in ('bfpixel', 'boyfriendpixel')]
    if not candidates:
        candidates = [p for p in icons.rglob('*.png') if 'bf' in p.stem.lower() and 'pixel' in p.stem.lower()]
    if not candidates:
        raise RuntimeError('PixelatedIcon source for boyfriend not found')
    png = sorted(candidates, key=lambda p: (len(str(p)), str(p)))[0]
    xml = png.with_suffix('.xml')
    if not xml.is_file():
        raise RuntimeError(f'animated BF PixelatedIcon XML missing next to {png}')
    return png, xml


def icon_frames(root: Path) -> tuple[list[Image.Image], Image.Image, str]:
    png, xml = find_bf_pixel_icon(root)
    nodes = list(ET.parse(xml).getroot())
    idle = [n for n in nodes if n.attrib.get('name', '').lower().startswith('idle0')]
    confirm = [n for n in nodes if n.attrib.get('name', '').lower().startswith('confirm0')]
    if not idle:
        idle = nodes[:]
    # Remove exact duplicate atlas records while preserving animation order.
    unique_nodes = []
    seen = set()
    for n in idle:
        key = tuple(n.attrib.get(k, '') for k in ('x','y','width','height','frameX','frameY','frameWidth','frameHeight'))
        if key not in seen:
            seen.add(key); unique_nodes.append(n)
    if not unique_nodes:
        raise RuntimeError('BF PixelatedIcon has no usable idle frames')
    # Four source frames are enough for the authored 10fps icon cycle on PS1.
    while len(unique_nodes) < 4:
        unique_nodes += unique_nodes
    unique_nodes = unique_nodes[:4]
    frames = [reconstruct_sparrow_frame(png, n) for n in unique_nodes]
    confirm_image = reconstruct_sparrow_frame(png, confirm[0]) if confirm else frames[-1].copy()
    return frames, confirm_image, str(png.relative_to(root))


def flat_tint(image: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    image = image.convert('RGBA')
    out = Image.new('RGBA', image.size, (*color, 255))
    out.putalpha(image.getchannel('A'))
    return out


def shelf_pack(items: list[tuple[str, Image.Image]]) -> tuple[Image.Image, dict[str, list[int]]]:
    atlas = Image.new('RGBA', (CTRL_W, CTRL_H), (0, 0, 0, 0))
    rects: dict[str, list[int]] = {}
    x = 0; y = 0; row_h = 0
    for name, image in items:
        image = image.convert('RGBA')
        w, h = image.size
        if w > 128 or h > CTRL_H:
            raise RuntimeError(f'v7 control {name} too large: {image.size}')
        if x + w > CTRL_W:
            x = 0; y += row_h + 2; row_h = 0
        if y + h > CTRL_H:
            raise RuntimeError(f'v7 control atlas overflow on {name} at {(x,y,w,h)}')
        atlas.alpha_composite(image, (x, y))
        rects[name] = [x, y, w, h]
        x += w + 2
        row_h = max(row_h, h)
    return atlas, rects


def build_controls(root: Path) -> tuple[Image.Image, dict]:
    selector_path = root / 'images' / 'charSelect' / 'charSelector.png'
    if not selector_path.is_file():
        raise RuntimeError('charSelector.png missing')
    selector = Image.open(selector_path).convert('RGBA').resize(
        (round(124 * WORLD_SCALE), round(112 * WORLD_SCALE)), Image.Resampling.LANCZOS
    )
    dark = flat_tint(selector, (0x3C, 0x74, 0xF7))
    light = flat_tint(selector, (0x3E, 0xBB, 0xFF))
    yellow = flat_tint(selector, (0xFF, 0xFF, 0x00))
    orange = flat_tint(selector, (0xFF, 0xCC, 0x00))

    confirm = v5.first_sparrow_frame(v6, root, 'charSelectorConfirm.png', 'charSelectorConfirm.xml')
    deny = v5.first_sparrow_frame(v6, root, 'charSelectorDenied.png', 'charSelectorDenied.xml')
    confirm = crop_alpha(confirm).resize(selector.size, Image.Resampling.LANCZOS) if confirm is not None else yellow.copy()
    deny = crop_alpha(deny).resize(selector.size, Image.Resampling.LANCZOS) if deny is not None else yellow.copy()

    icon_src, icon_confirm_src, icon_path = icon_frames(root)
    logical_w, logical_h = icon_src[0].size
    # PixelatedIcon.setCharacter() uses scale=2. Char Select later uses 2.6
    # when selected. Store the 2x/PS1 base size and let PS1 enlarge to 1.3x.
    icon_base_size = (max(1, round(logical_w * 2 / 3)), max(1, round(logical_h * 2 / 3)))
    icons = [im.resize(icon_base_size, Image.Resampling.NEAREST) for im in icon_src]
    icon_confirm = icon_confirm_src.resize(icon_base_size, Image.Resampling.NEAREST)

    bf_name = Image.open(root / 'images' / 'charSelect' / 'boyfriendNametag.png').convert('RGBA')
    locked_name = Image.open(root / 'images' / 'charSelect' / 'lockedNametag.png').convert('RGBA')
    # The PC tag occupies ~30% of a 1280px screen after its 0.77 scale. Mapping
    # that percentage to 320px is 1/4, not the 1/3 world crop used by v6.
    tag_scale = 0.77 * (W / SOURCE_W)
    bf_name = bf_name.resize((max(1, round(bf_name.width * tag_scale)), max(1, round(bf_name.height * tag_scale))), Image.Resampling.LANCZOS)
    locked_name = locked_name.resize((max(1, round(locked_name.width * tag_scale)), max(1, round(locked_name.height * tag_scale))), Image.Resampling.LANCZOS)

    items: list[tuple[str, Image.Image]] = []
    for i, im in enumerate(icons): items.append((f'icon_idle_{i}', im))
    items += [
        ('icon_confirm', icon_confirm),
        ('cursor_dark', dark), ('cursor_light', light), ('cursor_yellow', yellow),
        ('cursor_orange', orange), ('cursor_confirm', confirm), ('cursor_deny', deny),
        ('name_bf', bf_name), ('name_locked', locked_name),
    ]
    atlas, rects = shelf_pack(items)

    cursor_xy = []
    for index in range(9):
        cx = (index % 3) - 1; cy = (index // 3) - 1
        sx = CURSOR_FACTOR * cx + SOURCE_W / 2 - 124 / 2 + CURSOR_OFFSET_X
        sy = CURSOR_FACTOR * cy + SOURCE_H / 2 - 112 / 2 + CURSOR_OFFSET_Y
        cursor_xy.append([round((sx - CROP_X) * WORLD_SCALE), round(sy * WORLD_SCALE)])

    cell_x = GRID_X + GRID_X_SPREAD
    cell_y = GRID_Y + GRID_Y_SPREAD
    origin_x = 100.0
    origin_y = logical_h / 2.0
    def icon_dst(scale: float) -> list[int]:
        left = cell_x + origin_x - origin_x * scale
        top = cell_y + origin_y - origin_y * scale
        return [
            round((left - CROP_X) * WORLD_SCALE), round(top * WORLD_SCALE),
            round(logical_w * scale * WORLD_SCALE), round(logical_h * scale * WORLD_SCALE),
        ]

    # Preserve official midpoint concept but adapt the size to PS1 screen width.
    name_mid_x = round(1008 * (W / SOURCE_W))
    name_mid_y = round(100 * (H / SOURCE_H))
    def name_pos(image: Image.Image) -> list[int]:
        return [name_mid_x - image.width // 2, name_mid_y - image.height // 2]

    return atlas, {
        'rects': rects,
        'cursor_positions': cursor_xy,
        'icon_path': icon_path,
        'icon_idle_count': len(icons),
        'icon_unselected_dst': icon_dst(2.0),
        'icon_selected_dst': icon_dst(2.6),
        'name_bf_pos': name_pos(bf_name),
        'name_locked_pos': name_pos(locked_name),
        'tag_effective_scale': tag_scale,
    }


def macro_rect(name: str, rect: list[int]) -> list[str]:
    x, y, w, h = rect
    return [f'#define {name}_X {x}', f'#define {name}_Y {y}', f'#define {name}_W {w}', f'#define {name}_H {h}']


def write_header(path: Path, bg_count: int, meta: dict) -> None:
    r = meta['rects']
    lines = [
        '#ifndef CHARSELECT_V7_GENERATED_H', '#define CHARSELECT_V7_GENERATED_H', '',
        f'#define CSV7_BG_FRAME_COUNT {bg_count}',
        f'#define CSV7_ICON_IDLE_COUNT {meta["icon_idle_count"]}', '',
    ]
    for i in range(meta['icon_idle_count']):
        lines += macro_rect(f'CSV7_ICON_IDLE_{i}', r[f'icon_idle_{i}'])
    lines += macro_rect('CSV7_ICON_CONFIRM', r['icon_confirm'])
    for macro, key in (
        ('CSV7_CURSOR_DARK','cursor_dark'), ('CSV7_CURSOR_LIGHT','cursor_light'),
        ('CSV7_CURSOR_YELLOW','cursor_yellow'), ('CSV7_CURSOR_ORANGE','cursor_orange'),
        ('CSV7_CURSOR_CONFIRM','cursor_confirm'), ('CSV7_CURSOR_DENY','cursor_deny'),
        ('CSV7_NAME_BF','name_bf'), ('CSV7_NAME_LOCKED','name_locked'),
    ):
        lines += macro_rect(macro, r[key])
    ux, uy, uw, uh = meta['icon_unselected_dst']
    sx, sy, sw, sh = meta['icon_selected_dst']
    lines += [
        '', f'#define CSV7_ICON_UNSEL_X {ux}', f'#define CSV7_ICON_UNSEL_Y {uy}',
        f'#define CSV7_ICON_UNSEL_W {uw}', f'#define CSV7_ICON_UNSEL_H {uh}',
        f'#define CSV7_ICON_SEL_X {sx}', f'#define CSV7_ICON_SEL_Y {sy}',
        f'#define CSV7_ICON_SEL_W {sw}', f'#define CSV7_ICON_SEL_H {sh}',
        f'#define CSV7_NAME_BF_DST_X {meta["name_bf_pos"][0]}',
        f'#define CSV7_NAME_BF_DST_Y {meta["name_bf_pos"][1]}',
        f'#define CSV7_NAME_LOCKED_DST_X {meta["name_locked_pos"][0]}',
        f'#define CSV7_NAME_LOCKED_DST_Y {meta["name_locked_pos"][1]}', '',
        'static const s16 csv7_cursor_x[9] = {' + ', '.join(str(p[0]) for p in meta['cursor_positions']) + '};',
        'static const s16 csv7_cursor_y[9] = {' + ', '.join(str(p[1]) for p in meta['cursor_positions']) + '};',
        'static const s16 csv7_icon_src_x[CSV7_ICON_IDLE_COUNT] = {' + ', '.join(str(r[f'icon_idle_{i}'][0]) for i in range(meta['icon_idle_count'])) + '};',
        'static const s16 csv7_icon_src_y[CSV7_ICON_IDLE_COUNT] = {' + ', '.join(str(r[f'icon_idle_{i}'][1]) for i in range(meta['icon_idle_count'])) + '};',
        'static const s16 csv7_icon_src_w[CSV7_ICON_IDLE_COUNT] = {' + ', '.join(str(r[f'icon_idle_{i}'][2]) for i in range(meta['icon_idle_count'])) + '};',
        'static const s16 csv7_icon_src_h[CSV7_ICON_IDLE_COUNT] = {' + ', '.join(str(r[f'icon_idle_{i}'][3]) for i in range(meta['icon_idle_count'])) + '};',
        '', '#endif', '',
    ]
    path.write_text('\n'.join(lines))


def composite_preview(bg: Image.Image, char: Image.Image, fg: Image.Image, grid: Image.Image,
                      controls: Image.Image, meta: dict, state: int, icon_frame: int) -> Image.Image:
    out = bg.convert('RGBA').copy()
    out.alpha_composite(char.convert('RGBA'))
    out.alpha_composite(fg.convert('RGBA'))
    out.alpha_composite(grid.convert('RGBA'))
    r = meta['rects']
    icon_rect = r[f'icon_idle_{icon_frame % meta["icon_idle_count"]}']
    icon = controls.crop((icon_rect[0], icon_rect[1], icon_rect[0]+icon_rect[2], icon_rect[1]+icon_rect[3]))
    dst = meta['icon_selected_dst'] if state == BF_SLOT else meta['icon_unselected_dst']
    icon = icon.resize((dst[2], dst[3]), Image.Resampling.NEAREST)
    out.alpha_composite(icon, (dst[0], dst[1]))
    cx, cy = meta['cursor_positions'][state]
    cursor_rect = r['cursor_yellow']
    cursor = controls.crop((cursor_rect[0], cursor_rect[1], cursor_rect[0]+cursor_rect[2], cursor_rect[1]+cursor_rect[3]))
    out.alpha_composite(cursor, (cx, cy))
    name_key = 'name_bf' if state == BF_SLOT else 'name_locked'
    name_rect = r[name_key]
    name = controls.crop((name_rect[0], name_rect[1], name_rect[0]+name_rect[2], name_rect[1]+name_rect[3]))
    pos = meta['name_bf_pos'] if state == BF_SLOT else meta['name_locked_pos']
    out.alpha_composite(name, tuple(pos))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--builder', type=Path, required=True)
    ap.add_argument('--assets-root', type=Path, required=True)
    ap.add_argument('--upstream', type=Path, required=True)
    ap.add_argument('--report', type=Path, required=True)
    args = ap.parse_args()

    clean = corrected_builder_copy(args.builder)
    mod = load_builder(clean)
    mod.SCENE_W = W; mod.SCENE_H = H; mod.CHAR_W = W; mod.CHAR_H = H
    root = args.assets_root
    names = ['crowd','charSelectStage','barThing','bfChill','gfChill','lockedChill','charSelectSpeakers']
    anims = {name: mod.load_optional_anim(root, name) for name in names}
    missing = [n for n in ('crowd','charSelectStage','bfChill','gfChill','lockedChill','charSelectSpeakers') if anims.get(n) is None]
    if missing:
        raise RuntimeError(f'v7 official Animate assets missing: {missing}')

    rmse = traversal_rmse(mod, root)
    if rmse >= 115.0:
        raise RuntimeError(f'v7 BF hierarchy validation failed, RMSE={rmse:.3f}')

    menu = args.upstream / 'iso' / 'menu'; menu.mkdir(parents=True, exist_ok=True)
    bg_count, bg_frames, bg_blob, bg_records = build_bg_bank(mod, root, anims)
    bg_path = menu / 'csbg7.rle'; bg_path.write_bytes(bg_blob)

    modes = (
        [('idle', i, IDLE_COUNT) for i in range(IDLE_COUNT)] +
        [('locked', i, LOCKED_COUNT) for i in range(LOCKED_COUNT)] +
        [('confirm', i, CONFIRM_COUNT) for i in range(CONFIRM_COUNT)] +
        [('deny', i, DENY_COUNT) for i in range(DENY_COUNT)]
    )
    char_frames = [mod.build_character_overlay(root, anims, mode, i, count) for mode, i, count in modes]
    fg_frames = [build_foreground_overlay(mod, root, anims, i, count) for _mode, i, count in modes]
    char_records = [quantize_8bpp(x, mod.base.psx_color) for x in char_frames]
    fg_records = [quantize_8bpp(x, mod.base.psx_color) for x in fg_frames]
    char_blob = pack_csq2(char_records); fg_blob = pack_csq2(fg_records)
    if decode_csq2(char_blob) != char_records or decode_csq2(fg_blob) != fg_records:
        raise RuntimeError('v7 live bank lossless round-trip failed')
    char_path = menu / 'cschar8.rle'; fg_path = menu / 'csfg8.rle'
    char_path.write_bytes(char_blob); fg_path.write_bytes(fg_blob)
    live_total = len(bg_blob) + len(char_blob) + len(fg_blob)
    if live_total > LIVE_BANK_BUDGET:
        raise RuntimeError(f'v7 resident live-bank budget exceeded: {live_total}')

    grid, cells = build_grid(root)
    controls, control_meta = build_controls(root)

    grid_clut, grid_pixels = v6.rgba_to_indexed8(grid, mod.base.psx_color)
    xpix = 0
    grid_files = []
    for i, (vx, vy, width) in enumerate(GRID_PAGES):
        name = f'csgrid7{chr(ord("a")+i)}.tim'
        pixels = v6.split_page_pixels(grid_pixels, W, H, xpix, width)
        (menu / name).write_bytes(v6.tim8(grid_clut, pixels, width, H, vx, vy, *GRID_CLUT))
        grid_files.append(name); xpix += width

    ctrl_clut, ctrl_pixels = v6.rgba_to_indexed8(controls, mod.base.psx_color)
    ctrl_files = []
    for i, (vx, vy, width) in enumerate(CTRL_PAGES):
        name = f'csctrl7{chr(ord("a")+i)}.tim'
        pixels = v6.split_page_pixels(ctrl_pixels, CTRL_W, CTRL_H, i*128, width)
        (menu / name).write_bytes(v6.tim8(ctrl_clut, pixels, width, CTRL_H, vx, vy, *CTRL_CLUT))
        ctrl_files.append(name)

    write_header(args.upstream / 'src' / 'charselect_v7_generated.h', bg_count, control_meta)

    validation = args.report.parent / 'charselect_v7_validation'
    validation.mkdir(parents=True, exist_ok=True)
    bg_frames[0].save(validation / 'background_00.png')
    bg_frames[bg_count // 2].save(validation / 'background_mid.png')
    char_frames[0].save(validation / 'characters_idle_00.png')
    char_frames[min(1, len(char_frames)-1)].save(validation / 'characters_idle_01.png')
    grid.save(validation / 'grid_only.png')
    controls.save(validation / 'controls_atlas.png')
    composite_preview(bg_frames[0], char_frames[0], fg_frames[0], grid, controls, control_meta, 4, 0).save(validation / 'composite_bf_selected.png')
    composite_preview(bg_frames[1 % bg_count], char_frames[1], fg_frames[1], grid, controls, control_meta, 0, 1).save(validation / 'composite_top_left_locked.png')
    composite_preview(bg_frames[2 % bg_count], char_frames[2], fg_frames[2], grid, controls, control_meta, 8, 2).save(validation / 'composite_bottom_right_locked.png')
    placement = root / 'images' / 'charSelect' / 'placement.png'
    if placement.is_file():
        Image.open(placement).convert('RGBA').resize((W,H), Image.Resampling.LANCZOS).save(validation / 'official_placement_reference.png')

    report = json.loads(args.report.read_text()) if args.report.is_file() else {}
    report['character_select_source_v7'] = {
        'policy': 'source-correct renderer; no v6 fit-box/whole-lock-tint reconstruction',
        'animate_traversal': 'layers reversed, elements forward',
        'bf_reference_rmse': rmse,
        'background': {'file':'csbg7.rle','frames':bg_count,'packed_bytes':len(bg_blob),'sha256':sha256(bg_path),'update_target':'6-8fps genuine official timeline samples'},
        'characters': {'file':'cschar8.rle','frames':FRAME_COUNT,'packed_bytes':len(char_blob),'sha256':sha256(char_path)},
        'foreground': {'file':'csfg8.rle','frames':FRAME_COUNT,'packed_bytes':len(fg_blob),'sha256':sha256(fg_path)},
        'resident_live_bank_bytes': live_total,
        'grid': {'official_origin':[GRID_X,GRID_Y],'official_spread':[GRID_X_SPREAD,GRID_Y_SPREAD],'cells_source':cells,'files':grid_files,'lock_source':'locks.png/xml logical 122x133 authored variants'},
        'controls': {**control_meta,'files':ctrl_files,'nametag_policy':'0.77 authored scale adapted by 320/1280 screen width'},
        'validation_dir': str(validation),
    }
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(f'v7 hierarchy RMSE: {rmse:.3f} (current double-reversed baseline was ~120.567)')
    print(f'v7 background: {bg_count} genuine frames, {len(bg_blob)} bytes')
    print(f'v7 character bank: {len(char_blob)} bytes; foreground: {len(fg_blob)} bytes')
    print(f'v7 resident live banks total: {live_total} bytes')
    print(f'v7 PixelatedIcon source: {control_meta["icon_path"]}')
    print('v7 validation PNGs:', ', '.join(p.name for p in sorted(validation.glob('*.png'))))


if __name__ == '__main__':
    main()
