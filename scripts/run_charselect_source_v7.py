#!/usr/bin/env python3
"""Launch the source-correct Character Select v7 asset builder.

This adapter supplies two source-specific behaviors without modifying the older
working conversion modules:
- direct Sparrow sampling for one-shot selector effects,
- Lock.hx-compatible tinting of only the Animate layer named ``color``.
"""
from __future__ import annotations

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


def source_layered_lock_frames(root: Path) -> list[Image.Image]:
    """Recreate Lock.hx: tint only the Animate layer named ``color``."""
    if _builder_mod is None:
        raise RuntimeError('v7 builder module was not captured before lock rendering')
    mod = _builder_mod
    asset = mod.load_optional_anim(root, 'lock')
    if asset is None or 'lock' not in asset.symbols:
        raise RuntimeError('official Animate lock/color-layer source missing')

    symbol = asset.symbols['lock']
    timeline = symbol.get('TL', {})
    original_layers = timeline.get('L', [])
    if not original_layers or not any(str(x.get('LN', '')).lower() == 'color' for x in original_layers):
        raise RuntimeError('official lock symbol has no color layer')

    original_stage = asset.stage_matrix
    pieces = []
    try:
        # The nested ``lock`` symbol is rendered in its own coordinate system;
        # the root stage matrix belongs to the outer exported movie clip.
        asset.stage_matrix = mod.IDENTITY
        for layer in reversed(original_layers):
            timeline['L'] = [layer]
            image, ox, oy = mod.render_symbol(asset, 0, 'lock')
            if image.getchannel('A').getbbox() is not None:
                pieces.append((str(layer.get('LN', '')), image.convert('RGBA'), ox, oy))
    finally:
        timeline['L'] = original_layers
        asset.stage_matrix = original_stage

    if not pieces:
        raise RuntimeError('official lock color/drop/outline layers rendered empty')
    min_x = min(ox for _name, _im, ox, _oy in pieces)
    min_y = min(oy for _name, _im, _ox, oy in pieces)
    max_x = max(ox + im.width for _name, im, ox, _oy in pieces)
    max_y = max(oy + im.height for _name, im, _ox, oy in pieces)
    width = max_x - min_x
    height = max_y - min_y
    if width < 20 or height < 20 or width > 220 or height > 220:
        raise RuntimeError(f'implausible source lock bounds {(width, height)}')

    result = []
    for rgb in LOCK_RGB:
        canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        for layer_name, image, ox, oy in pieces:
            draw = _flat_color(image, rgb) if layer_name.lower() == 'color' else image
            canvas.alpha_composite(draw, (ox - min_x, oy - min_y))
        result.append(canvas)
    print('v7 source lock layers:', [(n, im.size, ox, oy) for n, im, ox, oy in pieces])
    print('v7 logical lock size:', result[0].size)
    return result


v7.lock_frames = source_layered_lock_frames


if __name__ == '__main__':
    v7.main()
