#!/usr/bin/env python3
"""Run the v6 exact-coordinate builder with page-local control packing fixed."""
from pathlib import Path
from PIL import Image
import build_charselect_exact_ui_v6 as base


def pack_controls(mod, root: Path):
    selector_src = base.load_static(root, 'charSelector.png')
    if selector_src is None:
        raise RuntimeError('official charSelector.png missing')
    selector = base.resize_exact(base.alpha_crop(selector_src), base.SCALE)

    dark = base.tint_flat(selector, (0x3C, 0x74, 0xF7))
    light = base.tint_flat(selector, (0x3E, 0xBB, 0xFF))
    yellow = base.tint_flat(selector, (0xFF, 0xFF, 0x00))
    orange = base.tint_flat(selector, (0xFF, 0xCC, 0x00))

    accepted = base.load_cursor_frame(mod, root, 'charSelectorConfirm.png', 'charSelectorConfirm.xml')
    denied = base.load_cursor_frame(mod, root, 'charSelectorDenied.png', 'charSelectorDenied.xml')
    accepted = base.resize_exact(accepted, base.SCALE) if accepted is not None else yellow.copy()
    denied = base.resize_exact(denied, base.SCALE) if denied is not None else yellow.copy()

    bf_name = base.load_static(root, 'boyfriendNametag.png')
    locked_name = base.load_static(root, 'lockedNametag.png')
    if bf_name is None or locked_name is None:
        raise RuntimeError('official Character Select nametag artwork missing')
    bf_name = base.resize_exact(bf_name, 0.77 * base.SCALE)
    locked_name = base.resize_exact(locked_name, 0.77 * base.SCALE)

    items = [
        ('cursor_dark', dark), ('cursor_light', light), ('cursor_yellow', yellow),
        ('cursor_orange', orange), ('cursor_confirm', accepted), ('cursor_deny', denied),
        ('name_bf', bf_name), ('name_locked', locked_name),
    ]

    atlas = Image.new('RGBA', (base.CTRL_W, base.CTRL_H), (0, 0, 0, 0))
    rects = {}
    page = 0
    y = 0
    for name, image in items:
        w, h = image.size
        if w > 128 or h > base.CTRL_H:
            raise RuntimeError(f'{name} cannot fit a control page: {image.size}')
        if y + h > base.CTRL_H:
            page += 1
            y = 0
        if page > 1:
            raise RuntimeError(f'control atlas overflow while packing {name}; sizes={[i[1].size for i in items]}')
        x = page * 128
        atlas.alpha_composite(image, (x, y))
        rects[name] = [x, y, w, h]
        y += h + 2

    def tag_pos(img: Image.Image):
        source_w = img.width / base.SCALE
        source_h = img.height / base.SCALE
        left_source = 1008 - source_w / 2
        top_source = 100 - source_h / 2
        return (int(round((left_source - base.CROP_X) * base.SCALE)), int(round(top_source * base.SCALE)))

    sw, sh = selector_src.size
    cursor_xy = []
    for index in range(9):
        cx = (index % 3) - 1
        cy = (index // 3) - 1
        source_x = base.CURSOR_FACTOR * cx + base.SOURCE_W / 2 - sw / 2 + base.CURSOR_OFFSET_X
        source_y = base.CURSOR_FACTOR * cy + base.SOURCE_H / 2 - sh / 2 + base.CURSOR_OFFSET_Y
        cursor_xy.append([
            int(round((source_x - base.CROP_X) * base.SCALE)),
            int(round(source_y * base.SCALE)),
        ])

    meta = {
        'rects': rects,
        'cursor_positions': cursor_xy,
        'name_bf_pos': list(tag_pos(bf_name)),
        'name_locked_pos': list(tag_pos(locked_name)),
        'official': {
            'grid_origin': [base.GRID_X, base.GRID_Y],
            'grid_spread': [base.GRID_X_SPREAD, base.GRID_Y_SPREAD],
            'lock_offset': [base.LOCK_OFFSET_X, base.LOCK_OFFSET_Y],
            'bf_icon_size': [128, 128],
            'cursor_factor': base.CURSOR_FACTOR,
            'cursor_offset': [base.CURSOR_OFFSET_X, base.CURSOR_OFFSET_Y],
            'nametag_midpoint': [1008, 100],
            'nametag_scale': 0.77,
        },
    }
    return atlas, meta


base.pack_controls = pack_controls

if __name__ == '__main__':
    base.main()
