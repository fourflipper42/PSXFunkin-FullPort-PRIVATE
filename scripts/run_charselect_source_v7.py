#!/usr/bin/env python3
"""Launch the source-correct Character Select v7 asset builder.

This adapter supplies source-specific behavior without changing the older
working conversion modules:
- direct Sparrow sampling for selector effects,
- Lock.hx-compatible tinting of only Animate leaves descended from a layer
  named ``color``, while preserving the exported registration relative to the
  official `(230,110)` Lock.hx sprite offset,
- portable generated coordinate tables that do not depend on PSXFunkin's s16
  typedef being visible before the generated header is included,
- v7 UI/foreground declarations kept in the generated header so replacing the
  legacy background helper block cannot accidentally erase their scope.
"""
from __future__ import annotations

import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

import build_charselect_source_v7 as v7


LOCK_RGB = (
    (0x31, 0xF2, 0xA5), (0x20, 0xEC, 0xCD), (0x24, 0xD9, 0xE8),
    (0x20, 0xEC, 0xCD), (0x20, 0xC8, 0xD4), (0x20, 0x9B, 0xDD),
    (0x20, 0x9B, 0xDD), (0x23, 0x62, 0xC9), (0x24, 0x3F, 0xB9),
)
LOCK_OFFSET_X = 230
LOCK_OFFSET_Y = 110
LOCK_LOGICAL_W = 122
LOCK_LOGICAL_H = 133
_builder_mod = None


def direct_sparrow_frame(png: Path, xml: Path, i: int, count: int):
    nodes = list(ET.parse(xml).getroot())
    if not nodes:
        raise RuntimeError(f'empty Sparrow atlas: {xml}')
    index = min(len(nodes) - 1, max(0, (i * len(nodes)) // max(1, count)))
    return v7.reconstruct_sparrow_frame(png, nodes[index])


v7.v6.sparrow_frame = direct_sparrow_frame


_original_load_builder = v7.load_builder


def capture_builder(path: Path):
    global _builder_mod
    _builder_mod = _original_load_builder(path)
    return _builder_mod


v7.load_builder = capture_builder


def _flat_color(image: Image.Image, rgb: tuple[int, int, int]) -> Image.Image:
    image = image.convert('RGBA')
    out = Image.new('RGBA', image.size, (*rgb, 255))
    out.putalpha(image.getchannel('A'))
    return out


def _collect_tagged(asset, symbol_name: str, frame_no: int, parent, out, inherited_color=False, depth=0):
    """Source-order traversal that retains whether a leaf is under `color`."""
    mod = _builder_mod
    if depth > 32:
        raise RuntimeError(f'lock Animate recursion too deep in {asset.folder}')
    symbol = asset.symbols[symbol_name]
    duration = max(1, mod.symbol_duration(symbol))
    frame_no %= duration
    for layer in reversed(symbol.get('TL', {}).get('L', [])):
        fr = mod.active_frame(layer, frame_no)
        if fr is None:
            continue
        tagged_color = inherited_color or str(layer.get('LN', '')).lower() == 'color'
        # v7 validated Animate rule: layers reverse, elements forward.
        for element in fr.get('E', []):
            if 'ASI' in element:
                asi = element['ASI']
                name = str(asi.get('N', ''))
                if name in asset.sprites:
                    out.append((name, mod.mat_mul(parent, mod.element_matrix(asi)), tagged_color))
            elif 'SI' in element:
                si = element['SI']
                child = str(si.get('SN', ''))
                if child not in asset.symbols:
                    continue
                first = int(si.get('FF', 0) or 0)
                child_frame = frame_no + first if si.get('ST', 'G') == 'G' else first
                _collect_tagged(
                    asset, child, child_frame,
                    mod.mat_mul(parent, mod.element_matrix(si)), out,
                    tagged_color, depth + 1,
                )
    return out


def _render_tagged(asset, frame_no: int, rgb: tuple[int, int, int]):
    mod = _builder_mod
    leaves = _collect_tagged(asset, asset.root_symbol, frame_no, asset.stage_matrix, [])
    if not leaves:
        raise RuntimeError('official lock hierarchy rendered no leaves')
    bounds = []
    for name, matrix, _tagged in leaves:
        sp = asset.sprites[name]
        for x, y in ((0,0),(sp.w,0),(0,sp.h),(sp.w,sp.h)):
            bounds.append(mod.point(matrix, x, y))
    min_x = math.floor(min(x for x, _ in bounds)); min_y = math.floor(min(y for _, y in bounds))
    max_x = math.ceil(max(x for x, _ in bounds)); max_y = math.ceil(max(y for _, y in bounds))
    width = max(1, max_x - min_x); height = max(1, max_y - min_y)
    canvas = Image.new('RGBA', (width, height), (0,0,0,0))
    tagged_count = 0
    for name, matrix, tagged in leaves:
        sp = asset.sprites[name]
        crop = sp.image.crop((sp.x, sp.y, sp.x + sp.w, sp.y + sp.h))
        if sp.rotated:
            crop = crop.transpose(Image.Transpose.ROTATE_90)
        if tagged:
            crop = _flat_color(crop, rgb); tagged_count += 1
        a,b,c,d,tx,ty = matrix
        det = a*d - b*c
        if abs(det) < 1e-9:
            continue
        ia, ic = d/det, -c/det
        ib, id_ = -b/det, a/det
        rx = ia*(min_x-tx) + ic*(min_y-ty)
        ry = ib*(min_x-tx) + id_*(min_y-ty)
        warped = crop.transform(
            (width,height), Image.Transform.AFFINE,
            (ia,ic,rx,ib,id_,ry), resample=Image.Resampling.BICUBIC,
        )
        canvas.alpha_composite(warped)
    if tagged_count == 0:
        raise RuntimeError('lock hierarchy contained no leaves under `color` layer')
    return canvas, min_x, min_y, tagged_count


def source_layered_lock_frames(root: Path) -> list[Image.Image]:
    """Recreate Lock.hx tint + registration for each canonical grid cell."""
    if _builder_mod is None:
        raise RuntimeError('v7 builder module was not captured before lock rendering')
    mod = _builder_mod
    asset = mod.load_optional_anim(root, 'lock')
    if asset is None:
        raise RuntimeError('official Animate lock source missing')
    try:
        frame_no = mod.sample_frame(asset, 0, 1, 'LOCKED')
    except Exception:
        frame_no = 0

    raw = []
    geometry = None
    for rgb in LOCK_RGB:
        image, ox, oy, tagged_count = _render_tagged(asset, frame_no, rgb)
        bbox = image.getchannel('A').getbbox()
        if bbox is None:
            raise RuntimeError('official lock hierarchy was transparent')
        if image.width < 45 or image.height < 55 or image.width > 180 or image.height > 180:
            raise RuntimeError(f'implausible visible lock bounds: {(image.size, ox, oy, bbox)}')
        raw.append(image)
        geometry = (image.size, ox, oy, tagged_count, bbox)

    # Flixel draws a sprite at x - offset.x plus the Animate registration.
    # Preserve that difference inside a transparent logical canvas so build_grid
    # can place every lock at the same exact source grid x/y.
    reg_x = geometry[1] - LOCK_OFFSET_X
    reg_y = geometry[2] - LOCK_OFFSET_Y
    if not (-32 <= reg_x <= 96 and -32 <= reg_y <= 128):
        raise RuntimeError(f'implausible Lock.hx registration delta {(reg_x, reg_y)} from {geometry}')
    pad_left = max(0, reg_x)
    pad_top = max(0, reg_y)
    canvas_w = max(LOCK_LOGICAL_W, pad_left + raw[0].width)
    canvas_h = max(LOCK_LOGICAL_H, pad_top + raw[0].height)
    if canvas_w > 180 or canvas_h > 180:
        raise RuntimeError(f'v7 registered lock canvas too large {(canvas_w, canvas_h)}')

    rendered = []
    for image in raw:
        canvas = Image.new('RGBA', (canvas_w, canvas_h), (0,0,0,0))
        canvas.alpha_composite(image, (pad_left, pad_top))
        rendered.append(canvas)

    print('v7 registered lock:', geometry, 'frame', frame_no, 'root', asset.root_symbol,
          'registration_delta', (reg_x,reg_y), 'canvas', (canvas_w,canvas_h))
    return rendered


v7.lock_frames = source_layered_lock_frames


# The generated header is included after menu.c has loaded gfx.h, but before
# the replacement helper block. Keep all v7 state that those helpers require in
# this header so replacing the old v5/v6 background block cannot erase it.
_original_write_header = v7.write_header


def portable_write_header(path: Path, bg_count: int, meta: dict) -> None:
    _original_write_header(path, bg_count, meta)
    text = path.read_text()
    text = text.replace('static const s16 csv7_', 'static const short csv7_')
    if 'static const s16 csv7_' in text:
        raise RuntimeError('non-portable s16 v7 header type remains')

    scope = '''
/* v7 declarations deliberately live here: apply_charselect_source_v7 replaces
 * the old helper region that previously contained the v5 foreground constants
 * and v6 UI texture declarations. */
#define MENU_CS_HQ_FG_VRAM_X 576
#define MENU_CS_HQ_FG_VRAM_Y 256
#define MENU_CS_HQ_FG_CLUT_X 704
#define MENU_CS_HQ_FG_CLUT_Y 510

'''
    marker = '\n#endif\n'
    if text.count(marker) != 1:
        raise RuntimeError(f'unexpected v7 header guard count {text.count(marker)}')
    text = text.replace(marker, '\n' + scope + '#endif\n', 1)
    path.write_text(text)


v7.write_header = portable_write_header


if __name__ == '__main__':
    v7.main()
