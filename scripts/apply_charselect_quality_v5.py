#!/usr/bin/env python3
"""Apply Character Select quality v5 runtime corrections.

Fixes the v4 font VRAM collision, splits the official foreground from BF/GF,
and replaces the remaining low-resolution Character Select UI with a dedicated
8bpp official-art atlas. The already-confirmed stayFunky XA path is untouched.

The v5.1 hotfix converts the resident raw UI atlas into two ordinary PS1 8bpp
TIM pages. This avoids the custom tpage/CLUT path that rendered invisibly on
hardware/emulation and forces the Character Select UI into the top OT layer.
"""
from pathlib import Path
import struct
import sys


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one anchor, found {count}')
    return text.replace(old, new, 1)


def build_ui_tim(raw: bytes, page: int, x: int, y: int, clut_x: int, clut_y: int) -> bytes:
    if len(raw) != 512 + 256 * 240:
        raise RuntimeError(f'CSUI8.BIN has unexpected size {len(raw)}')
    if page not in (0, 1):
        raise ValueError(page)
    clut = raw[:512]
    pixels = raw[512:]
    half = bytearray()
    x0 = page * 128
    for row in range(240):
        start = row * 256 + x0
        half.extend(pixels[start:start + 128])
    if len(half) != 128 * 240:
        raise RuntimeError('UI TIM page extraction failed')

    out = bytearray()
    out.extend(struct.pack('<II', 0x10, 0x09))  # TIM + 8bpp + CLUT
    out.extend(struct.pack('<IHHHH', 12 + len(clut), clut_x, clut_y, 256, 1))
    out.extend(clut)
    out.extend(struct.pack('<IHHHH', 12 + len(half), x, y, 64, 240))
    out.extend(half)
    return bytes(out)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('usage: apply_charselect_quality_v5.py <upstream>')
    root = Path(sys.argv[1])
    menu_path = root / 'src' / 'menu.c'
    xml_path = root / 'funkin.xml'
    text = menu_path.read_text()

    # Build two conventional 128x240 8bpp TIM pages from the official-art UI
    # atlas produced by build_charselect_quality_v5.py. Each page fits exactly
    # in one 8bpp PS1 texture page and both intentionally share one CLUT.
    raw_ui_path = root / 'iso' / 'menu' / 'csui8.bin'
    raw_ui = raw_ui_path.read_bytes()
    left_tim = build_ui_tim(raw_ui, 0, 448, 256, 16, 511)
    right_tim = build_ui_tim(raw_ui, 1, 512, 256, 16, 511)
    (root / 'iso' / 'menu' / 'csui8a.tim').write_bytes(left_tim)
    (root / 'iso' / 'menu' / 'csui8b.tim').write_bytes(right_tim)

    text = once(
        text,
        '#define MENU_CS_HQ_CHAR_VRAM_X 768\n#define MENU_CS_HQ_CLUT_X 448',
        '#define MENU_CS_HQ_CHAR_VRAM_X 768\n#define MENU_CS_HQ_CHAR_VRAM_Y 256\n#define MENU_CS_HQ_CLUT_X 448',
        'character VRAM y constant',
    )

    text = once(
        text,
        'static IO_Data menu_cs_char_frames = NULL;\n',
        'static IO_Data menu_cs_char_frames = NULL;\nstatic IO_Data menu_cs_fg_frames = NULL;\n',
        'foreground bank declaration',
    )
    text = once(
        text,
        'static u8 menu_cs_uploaded_char_frame = 0xFF;\n',
        'static u8 menu_cs_uploaded_char_frame = 0xFF;\nstatic u8 menu_cs_uploaded_fg_frame = 0xFF;\n',
        'foreground frame id',
    )

    free_anchor = 'static void Menu_FreeCSFrames(void)\n{'
    helpers = r'''#define MENU_CS_HQ_FG_VRAM_X 576
#define MENU_CS_HQ_FG_VRAM_Y 256
#define MENU_CS_HQ_FG_CLUT_X 704
#define MENU_CS_HQ_FG_CLUT_Y 510

#define MENU_CS_UI_VRAM_X 448
#define MENU_CS_UI_VRAM_Y 256
#define MENU_CS_UI_CLUT_X 16
#define MENU_CS_UI_CLUT_Y 511
#define MENU_CS_UI_W 256
#define MENU_CS_UI_H 240
#define MENU_CS_UI_WORD_W (MENU_CS_UI_W / 2)

static Gfx_Tex menu_cs_ui_pages[2];

static void Menu_UploadCSHQUI(void)
{
	// CSUI8.BIN;1 remains the generated source atlas. Runtime uses two normal
	// TIM pages so Gfx_LoadTex owns tpage/CLUT setup exactly like other menus.
	IO_Data left = IO_Read("\\MENU\\CSUI8A.TIM;1");
	IO_Data right = IO_Read("\\MENU\\CSUI8B.TIM;1");
	if (left == NULL || right == NULL)
	{
		if (left != NULL) Mem_Free(left);
		if (right != NULL) Mem_Free(right);
		sprintf(error_msg, "[Menu_UploadCSHQUI] UI TIM pages missing");
		ErrorLock();
		return;
	}
	Gfx_LoadTex(&menu_cs_ui_pages[0], left, GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu_cs_ui_pages[1], right, GFX_LOADTEX_FREE);
}

static void Menu_CSDrawUIRect(const RECT *src, const RECT *dst)
{
	u8 page = (src->x >= 128) ? 1 : 0;
	RECT local = {src->x - (page ? 128 : 0), src->y, src->w, src->h};
	Gfx_DrawTex(&menu_cs_ui_pages[page], &local, dst);
}

static void Menu_CSDrawHQForeground(const RECT *dst)
{
	static const s16 widths[3] = {128, 128, 64};
	static const s16 offsets[3] = {0, 128, 256};
	for (u8 page = 0; page < 3; page++)
	{
		Gfx_Tex tex;
		tex.tim_mode = 1;
		tex.tpage = getTPage(1, 0, MENU_CS_HQ_FG_VRAM_X + page * 64, MENU_CS_HQ_FG_VRAM_Y);
		tex.clut = getClut(MENU_CS_HQ_FG_CLUT_X, MENU_CS_HQ_FG_CLUT_Y);
		tex.pxshift = 1;
		RECT src = {0, 0, widths[page], MENU_CS_HQ_H};
		s32 x0 = dst->x + ((s32)dst->w * offsets[page]) / MENU_CS_HQ_W;
		s32 x1 = dst->x + ((s32)dst->w * (offsets[page] + widths[page])) / MENU_CS_HQ_W;
		RECT part = {x0, dst->y, x1 - x0, dst->h};
		Gfx_DrawTex(&tex, &src, &part);
	}
}

'''
    if text.count(free_anchor) != 1:
        raise SystemExit(f'helper insertion anchor count {text.count(free_anchor)}')
    text = text.replace(free_anchor, helpers + free_anchor, 1)

    text = once(
        text,
        free_anchor,
        free_anchor + '''
	if (menu_cs_fg_frames != NULL)
	{
		Mem_Free(menu_cs_fg_frames);
		menu_cs_fg_frames = NULL;
	}
''',
        'foreground free path',
    )

    free_start = text.index(free_anchor)
    free_end = text.index('\n}\n', free_start) + 3
    free_body = text[free_start:free_end]
    reset = '\tmenu_cs_uploaded_char_frame = 0xFF;\n'
    if free_body.count(reset) != 1:
        raise SystemExit(f'foreground cache reset in free: expected one local anchor, found {free_body.count(reset)}')
    free_body = free_body.replace(
        reset,
        reset + '\tmenu_cs_uploaded_fg_frame = 0xFF;\n',
        1,
    )
    text = text[:free_start] + free_body + text[free_end:]

    old_load = r'''static void Menu_LoadCSFrames(void)
{
	Menu_FreeCSFrames();
	// The compact bank is now intro-only. Live background is uploaded once at
	// full native resolution before XA playback begins.
	menu_cs_frames = IO_Read("\\MENU\\CSANIM.RLE;1");
	Menu_UploadCSHQBackground();
	menu_cs_char_frames = IO_Read("\\MENU\\CSCHAR8.RLE;1");
	if (menu_cs_frames == NULL || menu_cs_char_frames == NULL)
	{
		sprintf(error_msg, "[Menu_LoadCSFrames] Character Select HQ banks missing");
		ErrorLock();
	}
	menu_cs_uploaded_frame = 0xFF;
	menu_cs_uploaded_char_frame = 0xFF;
}
'''
    new_load = r'''static void Menu_LoadCSFrames(void)
{
	Menu_FreeCSFrames();
	menu_cs_frames = IO_Read("\\MENU\\CSANIM.RLE;1");
	Menu_UploadCSHQBackground();
	Menu_UploadCSHQUI();
	menu_cs_char_frames = IO_Read("\\MENU\\CSCHAR8.RLE;1");
	menu_cs_fg_frames = IO_Read("\\MENU\\CSFG8.RLE;1");
	if (menu_cs_frames == NULL || menu_cs_char_frames == NULL || menu_cs_fg_frames == NULL)
	{
		sprintf(error_msg, "[Menu_LoadCSFrames] Character Select v5 banks missing");
		ErrorLock();
	}
	menu_cs_uploaded_frame = 0xFF;
	menu_cs_uploaded_char_frame = 0xFF;
	menu_cs_uploaded_fg_frame = 0xFF;
}
'''
    text = once(text, old_load, new_load, 'v5 load path')

    old_char = r'''static void Menu_SetCSCharFrame(u8 frame)
{
	if (menu_cs_char_frames == NULL)
		return;
	frame %= MENU_CS_CHAR_FRAME_COUNT;
	if (frame == menu_cs_uploaded_char_frame)
		return;

	u8 *record = (u8*)menu_cs_char_scratch;
	if (!Menu_CSQ2Decode(menu_cs_char_frames, frame, MENU_CS_CHAR_FRAME_COUNT, MENU_CS_CHAR_RECORD_BYTES, record))
	{
		sprintf(error_msg, "[Menu_SetCSCharFrame] corrupt HQ frame %d", frame);
		ErrorLock();
		return;
	}
	RECT clut_upload = {MENU_CS_HQ_CLUT_X, MENU_CS_HQ_CLUT_Y, 256, 1};
	RECT image_upload = {MENU_CS_HQ_CHAR_VRAM_X, 0, MENU_CS_CHAR_WORD_W, MENU_CS_CHAR_H};
	LoadImage(&clut_upload, (u32*)record);
	LoadImage(&image_upload, (u32*)(record + MENU_CS_CLUT_BYTES));
	DrawSync(0);
	menu_cs_uploaded_char_frame = frame;
}
'''
    new_char = r'''static void Menu_SetCSForegroundFrame(u8 frame)
{
	if (menu_cs_fg_frames == NULL)
		return;
	frame %= MENU_CS_CHAR_FRAME_COUNT;
	if (frame == menu_cs_uploaded_fg_frame)
		return;

	u8 *record = (u8*)menu_cs_char_scratch;
	if (!Menu_CSQ2Decode(menu_cs_fg_frames, frame, MENU_CS_CHAR_FRAME_COUNT, MENU_CS_CHAR_RECORD_BYTES, record))
	{
		sprintf(error_msg, "[Menu_SetCSForegroundFrame] corrupt HQ frame %d", frame);
		ErrorLock();
		return;
	}
	RECT clut_upload = {MENU_CS_HQ_FG_CLUT_X, MENU_CS_HQ_FG_CLUT_Y, 256, 1};
	RECT image_upload = {MENU_CS_HQ_FG_VRAM_X, MENU_CS_HQ_FG_VRAM_Y, MENU_CS_CHAR_WORD_W, MENU_CS_CHAR_H};
	LoadImage(&clut_upload, (u32*)record);
	LoadImage(&image_upload, (u32*)(record + MENU_CS_CLUT_BYTES));
	DrawSync(0);
	menu_cs_uploaded_fg_frame = frame;
}

static void Menu_SetCSCharFrame(u8 frame)
{
	if (menu_cs_char_frames == NULL)
		return;
	frame %= MENU_CS_CHAR_FRAME_COUNT;
	if (frame != menu_cs_uploaded_char_frame)
	{
		u8 *record = (u8*)menu_cs_char_scratch;
		if (!Menu_CSQ2Decode(menu_cs_char_frames, frame, MENU_CS_CHAR_FRAME_COUNT, MENU_CS_CHAR_RECORD_BYTES, record))
		{
			sprintf(error_msg, "[Menu_SetCSCharFrame] corrupt HQ frame %d", frame);
			ErrorLock();
			return;
		}
		RECT clut_upload = {MENU_CS_HQ_CLUT_X, MENU_CS_HQ_CLUT_Y, 256, 1};
		RECT image_upload = {MENU_CS_HQ_CHAR_VRAM_X, MENU_CS_HQ_CHAR_VRAM_Y, MENU_CS_CHAR_WORD_W, MENU_CS_CHAR_H};
		LoadImage(&clut_upload, (u32*)record);
		LoadImage(&image_upload, (u32*)(record + MENU_CS_CLUT_BYTES));
		DrawSync(0);
		menu_cs_uploaded_char_frame = frame;
	}
	Menu_SetCSForegroundFrame(frame);
}
'''
    text = once(text, old_char, new_char, 'separate live layer upload')

    text = once(
        text,
        'tex.tpage = getTPage(1, 0, MENU_CS_HQ_CHAR_VRAM_X + page * 64, 0);',
        'tex.tpage = getTPage(1, 0, MENU_CS_HQ_CHAR_VRAM_X + page * 64, MENU_CS_HQ_CHAR_VRAM_Y);',
        'character tpage y',
    )

    fg_sig = 'static void Menu_CSDrawForeground(void)\n{'
    text = once(text, fg_sig, 'static void Menu_CSDrawForegroundLegacy(void)\n{', 'legacy foreground rename')
    new_fg = 'static void Menu_CSDrawForeground(void)\n{\n\t// v5 foreground is the independent 320x240 8bpp layer.\n}\n\n'
    legacy_fg_sig = 'static void Menu_CSDrawForegroundLegacy(void)\n{'
    text = once(text, legacy_fg_sig, new_fg + legacy_fg_sig, 'HQ foreground wrapper')

    grid_sig = 'static void Menu_CSDrawGrid(void)\n{'
    text = once(text, grid_sig, 'static void Menu_CSDrawGridLegacy(void)\n{', 'legacy grid rename')
    new_grid = r'''static void Menu_CSDrawGrid(void)
{
	static const RECT lock_src[9] = {
		{0,0,48,48}, {48,0,48,48}, {128,0,48,48},
		{176,0,48,48}, {0,48,48,48}, {48,48,48,48},
		{128,48,48,48}, {176,48,48,48}, {0,96,48,48},
	};
	const RECT bf_icon = {48,96,48,48};

	for (u8 i = 0; i < 9; i++)
	{
		s32 x = 97 + (i % 3) * 36;
		s32 y = 40 + (i / 3) * 42;
		RECT dst = {x, y, 43, 43};
		Menu_CSDrawUIRect((i == 4) ? &bf_icon : &lock_src[i], &dst);
	}

	s32 sx = 97 + (menu_cs_grid % 3) * 36 - 10;
	s32 sy = 40 + (menu_cs_grid / 3) * 42 - 10;
	RECT selector_dst = {sx, sy, 64, 64};
	RECT main_src = {128,144,64,64};
	RECT light_src = {64,144,64,64};
	RECT dark_src = {0,144,64,64};
	Menu_CSDrawUIRect(&main_src, &selector_dst);
	RECT light_dst = {sx - 2, sy - 1, 64, 64};
	Menu_CSDrawUIRect(&light_src, &light_dst);
	RECT dark_dst = {sx - 4, sy - 2, 64, 64};
	Menu_CSDrawUIRect(&dark_src, &dark_dst);

	RECT name_src = (menu_cs_grid == 4) ? (RECT){0,208,128,32} : (RECT){128,208,128,32};
	RECT name_dst = {219,17,128,32};
	Menu_CSDrawUIRect(&name_src, &name_dst);
}

'''
    legacy_grid_sig = 'static void Menu_CSDrawGridLegacy(void)\n{'
    text = once(text, legacy_grid_sig, new_grid + legacy_grid_sig, 'HQ grid/UI wrapper')

    # Remove the old UI submission site and submit it immediately before the
    # live scene layers. Since the PS1 OT is LIFO, this guarantees that UI is
    # rendered last/on top of background, characters, and foreground.
    grid_call = 'Menu_CSDrawGrid();'
    if text.count(grid_call) != 1:
        raise SystemExit(f'live grid call: expected one anchor, found {text.count(grid_call)}')
    text = text.replace(grid_call, '/* Character Select UI submitted with HQ scene below */', 1)

    old_scene = '''\t\t\t\t// OT is LIFO. Submission order here renders as:\n\t\t\t\t// 16bpp background -> 8bpp BF/GF + official foreground -> UI.\n\t\t\t\tMenu_CSDrawHQ8(&scene_dst);\n\t\t\t\tMenu_CSDrawHQ16(&scene_dst);'''
    new_scene = '''\t\t\t\t// OT is LIFO. UI is submitted first so it renders last/on top.\n\t\t\t\tMenu_CSDrawGrid();\n\t\t\t\tMenu_CSDrawHQForeground(&scene_dst);\n\t\t\t\tMenu_CSDrawHQ8(&scene_dst);\n\t\t\t\tMenu_CSDrawHQ16(&scene_dst);'''
    text = once(text, old_scene, new_scene, 'v5.1 scene layer order')

    menu_path.write_text(text)

    xml = xml_path.read_text()
    char_entry = '\t\t\t\t<file name = "cschar8.rle" type = "data" source = "iso/menu/cschar8.rle"/>\n'
    if xml.count(char_entry) != 1:
        raise SystemExit(f'cschar8.rle XML entry count {xml.count(char_entry)}')
    xml = xml.replace(
        char_entry,
        char_entry +
        '\t\t\t\t<file name = "csfg8.rle" type = "data" source = "iso/menu/csfg8.rle"/>\n' +
        '\t\t\t\t<file name = "csui8.bin" type = "data" source = "iso/menu/csui8.bin"/>\n' +
        '\t\t\t\t<file name = "csui8a.tim" type = "data" source = "iso/menu/csui8a.tim"/>\n' +
        '\t\t\t\t<file name = "csui8b.tim" type = "data" source = "iso/menu/csui8b.tim"/>\n',
        1,
    )
    xml_path.write_text(xml)

    low = text.lower()
    required = [
        '#define menu_cs_hq_char_vram_y 256',
        '#define menu_cs_hq_fg_vram_x 576',
        '#define menu_cs_ui_vram_x 448',
        'menu_uploadcshqui', 'csui8.bin;1', 'csui8a.tim;1', 'csui8b.tim;1', 'csfg8.rle;1',
        'gfx_loadtex(&menu_cs_ui_pages[0]', 'gfx_loadtex(&menu_cs_ui_pages[1]',
        'menu_setcsforegroundframe', 'menu_csdrawhqforeground',
        'rect name_dst = {219,17,128,32}',
    ]
    for marker in required:
        if marker not in low:
            raise SystemExit(f'quality v5.1 runtime missing {marker}')
    if 'menu_cs_hq_char_vram_x, 0, menu_cs_char_word_w' in low:
        raise SystemExit('v4 y=0 character upload remains and would corrupt the font')
    if 'menu_cs_hq_char_vram_x + page * 64, 0)' in low:
        raise SystemExit('v4 y=0 character tpage remains and would sample the font region')
    if 'stageid_8_' in low or 'spaghetti' in low:
        raise SystemExit('later milestone content leaked into Character Select v5.1')

    # Validate the two generated TIMs structurally before compilation.
    for name, expected_x in (('csui8a.tim', 448), ('csui8b.tim', 512)):
        blob = (root / 'iso' / 'menu' / name).read_bytes()
        magic, flags = struct.unpack_from('<II', blob, 0)
        if (magic, flags) != (0x10, 0x09):
            raise RuntimeError(f'{name}: bad TIM header {(magic, flags)}')
        clut_len, cx, cy, cw, ch = struct.unpack_from('<IHHHH', blob, 8)
        image_off = 8 + clut_len
        image_len, ix, iy, iw, ih = struct.unpack_from('<IHHHH', blob, image_off)
        if (cx, cy, cw, ch) != (16, 511, 256, 1):
            raise RuntimeError(f'{name}: bad CLUT rect {(cx, cy, cw, ch)}')
        if (ix, iy, iw, ih) != (expected_x, 256, 64, 240):
            raise RuntimeError(f'{name}: bad image rect {(ix, iy, iw, ih)}')
        if image_len != 12 + 128 * 240:
            raise RuntimeError(f'{name}: bad image block length {image_len}')

    print('Applied Character Select quality v5.1: standard TIM UI pages, fixed OT placement, font-safe HQ layers')


if __name__ == '__main__':
    main()
