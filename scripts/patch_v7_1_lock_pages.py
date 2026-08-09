#!/usr/bin/env python3
"""Expand v7.1 locks to one 128x128 page per animation state."""
from pathlib import Path


def rep(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected 1 anchor, found {n}")
    return text.replace(old, new, 1)

builder = Path('scripts/build_charselect_v7_1_cleanup.py')
s = builder.read_text()
s = rep(s,
    "LOCK_PAGES = ((768, 0, 128), (832, 0, 128))",
    "LOCK_PAGES = ((768, 0, 128), (832, 0, 128), (960, 0, 128))",
    'lock page map')
s = rep(s,
    "atlas = Image.new('RGBA', (256, 128), (0, 0, 0, 0))",
    "atlas = Image.new('RGBA', (384, 128), (0, 0, 0, 0))",
    'lock atlas width')
s = rep(s,
'''    for state, frame_no in enumerate(frame_nums):
        page = state >> 1
        base_x = 128 * page
        row_base = (state & 1) * 58
        for index, color in enumerate(LOCK_COLORS):''',
'''    for state, frame_no in enumerate(frame_nums):
        # One full 128x128 texture page per authored lock state. Selected/clicked
        # frames are substantially larger than idle and must not share a page.
        page = state
        base_x = 128 * page
        for index, color in enumerate(LOCK_COLORS):''',
    'lock state page selection')
s = rep(s,
'''            col = index % 3; row = index // 3
            slot_x = base_x + col * 40 + 4
            slot_y = row_base + row * 18
            if state == 2:
                slot_y = row * 38 + 4
            if slot_x + sw > base_x + 128 or slot_y + sh > 128:
                raise RuntimeError(f'lock atlas overflow state={state} index={index} size={im.size}')''',
'''            col = index % 3; row = index // 3
            if sw > 40 or sh > 40:
                raise RuntimeError(f'lock state exceeds 40x40 page cell state={state} index={index} size={im.size}')
            slot_x = base_x + col * 42 + 1
            slot_y = row * 42 + 1
            if slot_x + sw > base_x + 128 or slot_y + sh > 128:
                raise RuntimeError(f'lock atlas overflow state={state} index={index} size={im.size}')''',
    'lock page cell packing')
s = rep(s,
    "data=tim8_page(lclut,lpix,256,128,i*128,128,vx,vy,*LOCK_CLUT)",
    "data=tim8_page(lclut,lpix,384,128,i*128,128,vx,vy,*LOCK_CLUT)",
    'lock TIM page source width')
s = rep(s,
    "'files':['cslock71a.tim','cslock71b.tim']",
    "'files':['cslock71a.tim','cslock71b.tim','cslock71c.tim']",
    'lock report files')
s = rep(s,
    "('lock1',(832,0,64,128)),\n                 ('ctrl0'",
    "('lock1',(832,0,64,128)),('lock2',(960,0,64,128)),\n                 ('ctrl0'",
    'VRAM audit third lock page')
builder.write_text(s)

runtime = Path('scripts/apply_charselect_v7_1_cleanup.py')
s = runtime.read_text()
s = rep(s,
'''\tIO_Data l0 = IO_Read("\\\\MENU\\\\CSLOCK71A.TIM;1");
\tIO_Data l1 = IO_Read("\\\\MENU\\\\CSLOCK71B.TIM;1");
\tIO_Data c0 = IO_Read("\\\\MENU\\\\CSCTRL71A.TIM;1");''',
'''\tIO_Data l0 = IO_Read("\\\\MENU\\\\CSLOCK71A.TIM;1");
\tIO_Data l1 = IO_Read("\\\\MENU\\\\CSLOCK71B.TIM;1");
\tIO_Data l2 = IO_Read("\\\\MENU\\\\CSLOCK71C.TIM;1");
\tIO_Data c0 = IO_Read("\\\\MENU\\\\CSCTRL71A.TIM;1");''',
    'third lock read')
s = rep(s,
    'if (l0 == NULL || l1 == NULL || c0 == NULL || c1 == NULL)',
    'if (l0 == NULL || l1 == NULL || l2 == NULL || c0 == NULL || c1 == NULL)',
    'third lock validity')
s = rep(s,
'''\t\tif (l0 != NULL) Mem_Free(l0); if (l1 != NULL) Mem_Free(l1);
\t\tif (c0 != NULL) Mem_Free(c0); if (c1 != NULL) Mem_Free(c1);''',
'''\t\tif (l0 != NULL) Mem_Free(l0); if (l1 != NULL) Mem_Free(l1); if (l2 != NULL) Mem_Free(l2);
\t\tif (c0 != NULL) Mem_Free(c0); if (c1 != NULL) Mem_Free(c1);''',
    'third lock failed-read free')
s = rep(s,
'''\tGfx_LoadTex(&menu_cs_grid_v7[0], l0, GFX_LOADTEX_FREE);
\tGfx_LoadTex(&menu_cs_grid_v7[1], l1, GFX_LOADTEX_FREE);
\tGfx_LoadTex(&menu_cs_ctrl_v7[0], c0, GFX_LOADTEX_FREE);''',
'''\tGfx_LoadTex(&menu_cs_grid_v7[0], l0, GFX_LOADTEX_FREE);
\tGfx_LoadTex(&menu_cs_grid_v7[1], l1, GFX_LOADTEX_FREE);
\tGfx_LoadTex(&menu_cs_grid_v7[2], l2, GFX_LOADTEX_FREE);
\tGfx_LoadTex(&menu_cs_ctrl_v7[0], c0, GFX_LOADTEX_FREE);''',
    'third lock load')
s = rep(s,
'''\tu8 page=(sx>=128)?1:0;
\tRECT src={sx-(page?128:0),sy,sw,sh};''',
'''\tu8 page=(u8)(sx / 128);
\tRECT src={sx-(page * 128),sy,sw,sh};''',
    'three-page lock draw')
s = rep(s,
    "('csintro71.rle','cslock71a.tim','cslock71b.tim','csctrl71a.tim','csctrl71b.tim')",
    "('csintro71.rle','cslock71a.tim','cslock71b.tim','cslock71c.tim','csctrl71a.tim','csctrl71b.tim')",
    'third lock XML entry')
runtime.write_text(s)

print('Patched v7.1 lock atlas to three independent 128x128 pages.')
