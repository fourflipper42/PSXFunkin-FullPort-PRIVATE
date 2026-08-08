#!/usr/bin/env python3
"""Build Character Select v6 UI from the exact official v0.8.4 coordinates.

The previous v5 atlas forced unrelated assets into guessed 48/64/128 pixel
cells.  v6 instead renders the grid at the original 1280x720 coordinates used
by CharSelectSubState.hx, then performs the single 4:3 PS1 crop/downsample.
Cursor and nametag assets keep their original authored dimensions and official
scale/position math.  Output is standard 8bpp TIM pages only.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path

from PIL import Image

from build_charselect_quality_v5 import (
    LOCK_COLORS,
    alpha_crop,
    clean_builder_copy,
    first_sparrow_frame,
    load_module,
    load_static,
    render_icon,
    tint_flat,
    tint_keep_luma,
)

SCREEN_W = 320
SCREEN_H = 240
SOURCE_W = 1280
SOURCE_H = 720
CROP_X = 160
CROP_W = 960
SCALE = 1.0 / 3.0

GRID_X = 450
GRID_Y = 120
GRID_X_SPREAD = 107
GRID_Y_SPREAD = 127
LOCK_OFFSET_X = 230
LOCK_OFFSET_Y = 110
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


def ps1_crop(image: Image.Image) -> Image.Image:
    image = image.convert('RGBA')
    return image.crop((CROP_X, 0, CROP_X + CROP_W, SOURCE_H)).resize(
        (SCREEN_W, SCREEN_H), Image.Resampling.LANCZOS
    )


def resize_exact(image: Image.Image, scale: float, *, nearest: bool = False) -> Image.Image:
    image = image.convert('RGBA')
    w = max(1, int(round(image.width * scale)))
    h = max(1, int(round(image.height * scale)))
    return image.resize((w, h), Image.Resampling.NEAREST if nearest else Image.Resampling.LANCZOS)


def rgba_to_indexed8(image: Image.Image, psx_color) -> tuple[bytes, bytes]:
    image = image.convert('RGBA')
    alpha = image.getchannel('A')
    rgb = Image.new('RGB', image.size, (0, 0, 0))
    rgb.paste(image.convert('RGB'), mask=alpha)
    q = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw = q.getpalette()[:255 * 3]
    colors = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
    while len(colors) < 255:
        colors.append((0, 0, 0))
    clut = b''.join(struct.pack('<H', c) for c in ([0] + [psx_color(c) for c in colors[:255]]))
    qpix = list(q.getdata())
    apix = list(alpha.getdata())
    pixels = bytes(0 if a < 128 else int(idx) + 1 for idx, a in zip(qpix, apix))
    return clut, pixels


def tim8(clut: bytes, pixels: bytes, width: int, height: int, x: int, y: int, clut_x: int, clut_y: int) -> bytes:
    if len(clut) != 512:
        raise RuntimeError(f'8bpp CLUT size {len(clut)} != 512')
    if len(pixels) != width * height:
        raise RuntimeError(f'8bpp pixel size {len(pixels)} != {width * height}')
    if width & 1:
        raise RuntimeError('8bpp TIM width must be even')
    out = bytearray(struct.pack('<II', 0x10, 0x09))
    out.extend(struct.pack('<IHHHH', 12 + len(clut), clut_x, clut_y, 256, 1))
    out.extend(clut)
    out.extend(struct.pack('<IHHHH', 12 + len(pixels), x, y, width // 2, height))
    out.extend(pixels)
    return bytes(out)


def split_page_pixels(pixels: bytes, full_w: int, full_h: int, x0: int, width: int) -> bytes:
    out = bytearray()
    for y in range(full_h):
        row = y * full_w
        out.extend(pixels[row + x0:row + x0 + width])
    if len(out) != width * full_h:
        raise RuntimeError('page extraction failed')
    return bytes(out)


def render_grid(mod, root: Path) -> Image.Image:
    canvas = Image.new('RGBA', (SOURCE_W, SOURCE_H), (0, 0, 0, 0))
    lock_anim = mod.load_optional_anim(root, 'lock')
    if lock_anim is None:
        raise RuntimeError('official charSelect/lock atlas missing')

    for index in range(9):
        col = index % 3
        row = index // 3
        x = GRID_X + col * GRID_X_SPREAD
        y = GRID_Y + row * GRID_Y_SPREAD
        if index == BF_SLOT:
            # PixelatedIcon.setGraphicSize(128, 128) is explicit in v0.8.4.
            icon = render_icon(mod, root).resize((128, 128), Image.Resampling.NEAREST)
            canvas.alpha_composite(icon, (x, y))
            continue

        # Lock.hx uses offset.set(230, 110), so draw its authored atlas at
        # member position minus that offset instead of alpha-cropping/fitting it.
        one = Image.new('RGBA', (SOURCE_W, SOURCE_H), (0, 0, 0, 0))
        mod.paste_anim(one, lock_anim, x - LOCK_OFFSET_X, y - LOCK_OFFSET_Y, 0, 1)
        one = tint_keep_luma(one, LOCK_COLORS[index])
        canvas = Image.alpha_composite(canvas, one)

    return ps1_crop(canvas)


def load_cursor_frame(mod, root: Path, png: str, xml: str) -> Image.Image | None:
    frame = first_sparrow_frame(mod, root, png, xml)
    if frame is None:
        return None
    return alpha_crop(frame)


def pack_controls(mod, root: Path) -> tuple[Image.Image, dict]:
    selector = load_static(root, 'charSelector.png')
    if selector is None:
        raise RuntimeError('official charSelector.png missing')
    selector = resize_exact(alpha_crop(selector), SCALE)

    dark = tint_flat(selector, (0x3C, 0x74, 0xF7))
    light = tint_flat(selector, (0x3E, 0xBB, 0xFF))
    yellow = tint_flat(selector, (0xFF, 0xFF, 0x00))
    orange = tint_flat(selector, (0xFF, 0xCC, 0x00))

    accepted = load_cursor_frame(mod, root, 'charSelectorConfirm.png', 'charSelectorConfirm.xml')
    denied = load_cursor_frame(mod, root, 'charSelectorDenied.png', 'charSelectorDenied.xml')
    accepted = resize_exact(accepted, SCALE) if accepted is not None else yellow.copy()
    denied = resize_exact(denied, SCALE) if denied is not None else yellow.copy()

    bf_name = load_static(root, 'boyfriendNametag.png')
    locked_name = load_static(root, 'lockedNametag.png')
    if bf_name is None or locked_name is None:
        raise RuntimeError('official Character Select nametag artwork missing')
    bf_name = resize_exact(bf_name, 0.77 * SCALE)
    locked_name = resize_exact(locked_name, 0.77 * SCALE)

    items = [
        ('cursor_dark', dark), ('cursor_light', light), ('cursor_yellow', yellow),
        ('cursor_orange', orange), ('cursor_confirm', accepted), ('cursor_deny', denied),
        ('name_bf', bf_name), ('name_locked', locked_name),
    ]

    atlas = Image.new('RGBA', (CTRL_W, CTRL_H), (0, 0, 0, 0))
    rects: dict[str, list[int]] = {}
    x = 0
    y = 0
    row_h = 0
    for name, image in items:
        w, h = image.size
        if w > 128:
            raise RuntimeError(f'{name} width {w} exceeds one 8bpp page; keep controls page-local')
        if x + w > 128:
            x = 128
            y = 0
            row_h = 0
        # Keep every item entirely inside one 128px 8bpp texture page.
        page_end = 128 if x < 128 else 256
        if x + w > page_end:
            x = 128
            y = 0
            row_h = 0
        if y + h > CTRL_H:
            raise RuntimeError(f'control atlas overflow packing {name} at {(x, y, w, h)}')
        atlas.alpha_composite(image, (x, y))
        rects[name] = [x, y, w, h]
        y += h + 2
        row_h = max(row_h, h)

    # Nametag midpoint is (1008,100) after 0.77 scale in official code.
    def tag_pos(img: Image.Image) -> tuple[int, int]:
        source_w = img.width / SCALE
        source_h = img.height / SCALE
        left_source = 1008 - source_w / 2
        top_source = 100 - source_h / 2
        return (int(round((left_source - CROP_X) * SCALE)), int(round(top_source * SCALE)))

    selector_src = load_static(root, 'charSelector.png')
    assert selector_src is not None
    sw, sh = selector_src.size
    cursor_xy = []
    for index in range(9):
        cx = (index % 3) - 1
        cy = (index // 3) - 1
        source_x = CURSOR_FACTOR * cx + SOURCE_W / 2 - sw / 2 + CURSOR_OFFSET_X
        source_y = CURSOR_FACTOR * cy + SOURCE_H / 2 - sh / 2 + CURSOR_OFFSET_Y
        cursor_xy.append([
            int(round((source_x - CROP_X) * SCALE)),
            int(round(source_y * SCALE)),
        ])

    meta = {
        'rects': rects,
        'cursor_positions': cursor_xy,
        'name_bf_pos': list(tag_pos(bf_name)),
        'name_locked_pos': list(tag_pos(locked_name)),
        'official': {
            'grid_origin': [GRID_X, GRID_Y],
            'grid_spread': [GRID_X_SPREAD, GRID_Y_SPREAD],
            'lock_offset': [LOCK_OFFSET_X, LOCK_OFFSET_Y],
            'bf_icon_size': [128, 128],
            'cursor_factor': CURSOR_FACTOR,
            'cursor_offset': [CURSOR_OFFSET_X, CURSOR_OFFSET_Y],
            'nametag_midpoint': [1008, 100],
            'nametag_scale': 0.77,
        },
    }
    return atlas, meta


def write_header(path: Path, meta: dict) -> None:
    rects = meta['rects']
    positions = meta['cursor_positions']
    def macro_rect(name: str, key: str) -> str:
        x, y, w, h = rects[key]
        return f'#define {name}_X {x}\n#define {name}_Y {y}\n#define {name}_W {w}\n#define {name}_H {h}\n'

    lines = ['#ifndef CHARSELECT_UI_V6_GENERATED_H', '#define CHARSELECT_UI_V6_GENERATED_H', '']
    for macro, key in (
        ('CSV6_CURSOR_DARK', 'cursor_dark'), ('CSV6_CURSOR_LIGHT', 'cursor_light'),
        ('CSV6_CURSOR_YELLOW', 'cursor_yellow'), ('CSV6_CURSOR_ORANGE', 'cursor_orange'),
        ('CSV6_CURSOR_CONFIRM', 'cursor_confirm'), ('CSV6_CURSOR_DENY', 'cursor_deny'),
        ('CSV6_NAME_BF', 'name_bf'), ('CSV6_NAME_LOCKED', 'name_locked'),
    ):
        lines.append(macro_rect(macro, key).rstrip())
    lines += [
        f'#define CSV6_NAME_BF_DST_X {meta["name_bf_pos"][0]}',
        f'#define CSV6_NAME_BF_DST_Y {meta["name_bf_pos"][1]}',
        f'#define CSV6_NAME_LOCKED_DST_X {meta["name_locked_pos"][0]}',
        f'#define CSV6_NAME_LOCKED_DST_Y {meta["name_locked_pos"][1]}',
        '',
        'static const s16 csv6_cursor_x[9] = {' + ', '.join(str(v[0]) for v in positions) + '};',
        'static const s16 csv6_cursor_y[9] = {' + ', '.join(str(v[1]) for v in positions) + '};',
        '', '#endif', '',
    ]
    path.write_text('\n'.join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--builder', type=Path, required=True)
    ap.add_argument('--assets-root', type=Path, required=True)
    ap.add_argument('--upstream', type=Path, required=True)
    ap.add_argument('--report', type=Path, required=True)
    args = ap.parse_args()

    clean_path = clean_builder_copy(args.builder)
    mod = load_module(clean_path, 'charselect_v6_source')
    root = args.assets_root
    menu_dir = args.upstream / 'iso' / 'menu'
    menu_dir.mkdir(parents=True, exist_ok=True)

    grid = render_grid(mod, root)
    controls, meta = pack_controls(mod, root)

    grid_clut, grid_pixels = rgba_to_indexed8(grid, mod.base.psx_color)
    xpix = 0
    grid_files = []
    for idx, (vx, vy, width) in enumerate(GRID_PAGES):
        page = split_page_pixels(grid_pixels, SCREEN_W, SCREEN_H, xpix, width)
        name = f'csgrid6{chr(ord("a") + idx)}.tim'
        (menu_dir / name).write_bytes(tim8(grid_clut, page, width, SCREEN_H, vx, vy, *GRID_CLUT))
        grid_files.append(name)
        xpix += width
    if xpix != SCREEN_W:
        raise RuntimeError(f'grid page coverage {xpix} != {SCREEN_W}')

    ctrl_clut, ctrl_pixels = rgba_to_indexed8(controls, mod.base.psx_color)
    ctrl_files = []
    for idx, (vx, vy, width) in enumerate(CTRL_PAGES):
        page = split_page_pixels(ctrl_pixels, CTRL_W, CTRL_H, idx * 128, width)
        name = f'csctrl6{chr(ord("a") + idx)}.tim'
        (menu_dir / name).write_bytes(tim8(ctrl_clut, page, width, CTRL_H, vx, vy, *CTRL_CLUT))
        ctrl_files.append(name)

    write_header(args.upstream / 'src' / 'charselect_ui_v6_generated.h', meta)

    preview_dir = args.report.parent
    preview_dir.mkdir(parents=True, exist_ok=True)
    grid.save(preview_dir / 'charselect_v6_grid_preview.png')
    controls.save(preview_dir / 'charselect_v6_controls_preview.png')

    report = json.loads(args.report.read_text()) if args.report.is_file() else {}
    report['character_select_exact_ui_v6'] = {
        'policy': 'official v0.8.4 source-coordinate render; no guessed per-asset fit boxes',
        'grid_files': grid_files,
        'control_files': ctrl_files,
        'grid_size': [SCREEN_W, SCREEN_H],
        'control_atlas_size': [CTRL_W, CTRL_H],
        **meta,
    }
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('Built Character Select v6 exact UI from official source coordinates')
    print('Cursor positions:', meta['cursor_positions'])
    print('BF nametag position:', meta['name_bf_pos'])


if __name__ == '__main__':
    main()
