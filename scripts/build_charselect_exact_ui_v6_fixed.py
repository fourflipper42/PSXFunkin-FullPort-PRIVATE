#!/usr/bin/env python3
"""Run v6 exact-coordinate UI builder with lossless cross-page control packing.

Cursor graphics stay wholly inside one 128px 8bpp texture page. Official
nametags retain their exact PS1-scaled dimensions, even when they cross the
128px page boundary; the runtime splits those draws instead of shrinking art.
"""
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
    # Preserve the actual v0.8.4 0.77 nametag scale, then the single 1/3 PS1 scale.
    bf_name = base.resize_exact(bf_name, 0.77 * base.SCALE)
    locked_name = base.resize_exact(locked_name, 0.77 * base.SCALE)

    cursor_items = [
        ('cursor_dark', dark), ('cursor_light', light), ('cursor_yellow', yellow),
        ('cursor_orange', orange), ('cursor_confirm', accepted), ('cursor_deny', denied),
    ]

    atlas = Image.new('RGBA', (base.CTRL_W, base.CTRL_H), (0, 0, 0, 0))
    rects = {}

    # Reserve the bottom of both pages for the two authentic-width nametags.
    # They are allowed to cross x=128; the runtime splits the draw there.
    for name, image in (('name_bf', bf_name), ('name_locked', locked_name)):
        if image.width > base.CTRL_W or image.height > base.CTRL_H:
            raise RuntimeError(f'{name} exceeds complete control atlas: {image.size}')
    locked_y = base.CTRL_H - locked_name.height
    bf_y = locked_y - 2 - bf_name.height
    if bf_y < 0:
        raise RuntimeError(f'nametags do not fit vertically: bf={bf_name.size} locked={locked_name.size}')

    page_y = [0, 0]
    for name, image in cursor_items:
        w, h = image.size
        if w > 128:
            raise RuntimeError(f'{name} width {w} exceeds one cursor texture page')
        placed = False
        for page in range(2):
            if page_y[page] + h <= bf_y - 2:
                x = page * 128
                y = page_y[page]
                atlas.alpha_composite(image, (x, y))
                rects[name] = [x, y, w, h]
                page_y[page] = y + h + 2
                placed = True
                break
        if not placed:
            raise RuntimeError(
                f'cursor controls overflow reserved atlas area while packing {name}; '
                f'page_y={page_y} reserve_start={bf_y} size={image.size}'
            )

    atlas.alpha_composite(bf_name, (0, bf_y))
    atlas.alpha_composite(locked_name, (0, locked_y))
    rects['name_bf'] = [0, bf_y, bf_name.width, bf_name.height]
    rects['name_locked'] = [0, locked_y, locked_name.width, locked_name.height]

    def tag_pos(img: Image.Image):
        # img is already official 0.77 scale * PS1 1/3 scale. Dividing only by
        # PS1 SCALE recovers the actual 1280x720 display dimensions used when
        # centering around Nametag.hx midpoint (1008,100).
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
        'wide_control_split_x': 128,
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

# The generated header is included before menu.c's PSX typedef headers. Keep it
# self-contained by using standard C 'short' for these tiny screen coordinates
# instead of the project-local s16 typedef.
_original_write_header = base.write_header

def write_header_portable(path: Path, meta: dict) -> None:
    _original_write_header(path, meta)
    text = path.read_text()
    text = text.replace('static const s16 csv6_cursor_x', 'static const short csv6_cursor_x')
    text = text.replace('static const s16 csv6_cursor_y', 'static const short csv6_cursor_y')
    if 'static const s16 csv6_cursor_' in text:
        raise RuntimeError('non-portable s16 cursor type remains in generated v6 header')
    path.write_text(text)

base.write_header = write_header_portable

if __name__ == '__main__':
    base.main()
