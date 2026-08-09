#!/usr/bin/env python3
"""Apply the source-correct Character Select v7 runtime.

Run after v6. Working XA audio and the confirmed font-safe v5 VRAM placement are
left intact. v7 replaces only the live visual model: animated HQ background,
corrected source-order BF/GF banks, canonical grid, real PixelatedIcon,
source-based cursor motion and smaller PS1-adapted nametags.
"""
from pathlib import Path
import sys


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected one anchor, found {n}')
    return text.replace(old, new, 1)


def between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    a = text.find(start)
    if a < 0:
        raise SystemExit(f'{label}: start anchor missing')
    b = text.find(end, a + len(start))
    if b < 0:
        raise SystemExit(f'{label}: end anchor missing')
    return text[:a] + replacement + text[b:]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('usage: apply_charselect_source_v7.py <upstream>')
    root = Path(sys.argv[1])
    menu_path = root / 'src' / 'menu.c'
    xml_path = root / 'funkin.xml'
    text = menu_path.read_text()

    text = once(
        text,
        '#include "charselect_ui_v6_generated.h"\n',
        '#include "charselect_ui_v6_generated.h"\n#include "charselect_v7_generated.h"\n',
        'v7 generated header include',
    )
    text = once(
        text,
        'static IO_Data menu_cs_fg_frames = NULL;\n',
        'static IO_Data menu_cs_fg_frames = NULL;\nstatic IO_Data menu_cs_bg_frames = NULL;\n',
        'v7 background bank declaration',
    )
    text = once(
        text,
        'static u8 menu_cs_uploaded_fg_frame = 0xFF;\n',
        'static u8 menu_cs_uploaded_fg_frame = 0xFF;\nstatic u8 menu_cs_uploaded_bg_frame = 0xFF;\n',
        'v7 background frame cache',
    )
    text = once(
        text,
        'static Gfx_Tex menu_cs_grid_v6[3];\nstatic Gfx_Tex menu_cs_ctrl_v6[2];\n',
        'static Gfx_Tex menu_cs_grid_v7[3];\nstatic Gfx_Tex menu_cs_ctrl_v7[2];\n',
        'v7 UI textures',
    )

    # The old static 16bpp uploader becomes a resident lossless animated 8bpp
    # bank. It reuses the existing 77,312-byte HQ scratch buffer, so no large
    # new contiguous frame allocation is introduced.
    bg_start = 'static void Menu_UploadCSHQBackground(void)\n{'
    bg_end = 'static void Menu_UploadCSHQUI(void)\n{'
    bg_code = r'''#define MENU_CS_V7_BG_VRAM_X 448
#define MENU_CS_V7_BG_VRAM_Y 0
#define MENU_CS_V7_BG_CLUT_X 704
#define MENU_CS_V7_BG_CLUT_Y 509

/* Gfx_Tex must be declared in menu.c after gfx.h, never in the early generated header. */
static Gfx_Tex menu_cs_grid_v7[3];
static Gfx_Tex menu_cs_ctrl_v7[2];

static void Menu_SetCSV7BackgroundFrame(u8 frame)
{
	if (menu_cs_bg_frames == NULL)
		return;
	frame %= CSV7_BG_FRAME_COUNT;
	if (frame == menu_cs_uploaded_bg_frame)
		return;

	u8 *record = (u8*)menu_cs_char_scratch;
	if (!Menu_CSQ2Decode(menu_cs_bg_frames, frame, CSV7_BG_FRAME_COUNT, MENU_CS_CHAR_RECORD_BYTES, record))
	{
		sprintf(error_msg, "[Menu_SetCSV7BackgroundFrame] corrupt frame %d", frame);
		ErrorLock();
		return;
	}
	RECT clut_upload = {MENU_CS_V7_BG_CLUT_X, MENU_CS_V7_BG_CLUT_Y, 256, 1};
	RECT image_upload = {MENU_CS_V7_BG_VRAM_X, MENU_CS_V7_BG_VRAM_Y, MENU_CS_CHAR_WORD_W, MENU_CS_CHAR_H};
	LoadImage(&clut_upload, (u32*)record);
	LoadImage(&image_upload, (u32*)(record + MENU_CS_CLUT_BYTES));
	DrawSync(0);
	menu_cs_uploaded_bg_frame = frame;
}

static void Menu_UploadCSHQBackground(void)
{
	menu_cs_bg_frames = IO_Read("\\MENU\\CSBG7.RLE;1");
	if (menu_cs_bg_frames == NULL)
	{
		sprintf(error_msg, "[Menu_UploadCSHQBackground] CSBG7.RLE missing");
		ErrorLock();
		return;
	}
	menu_cs_uploaded_bg_frame = 0xFF;
	Menu_SetCSV7BackgroundFrame(0);
}

'''
    text = between(text, bg_start, bg_end, bg_code, 'v7 animated background runtime')

    upload_start = 'static void Menu_UploadCSHQUI(void)\n{'
    upload_end = 'static void Menu_CSDrawV6Control(const RECT *src, const RECT *dst)\n{'
    upload_code = r'''static void Menu_UploadCSHQUI(void)
{
	IO_Data g0 = IO_Read("\\MENU\\CSGRID7A.TIM;1");
	IO_Data g1 = IO_Read("\\MENU\\CSGRID7B.TIM;1");
	IO_Data g2 = IO_Read("\\MENU\\CSGRID7C.TIM;1");
	IO_Data c0 = IO_Read("\\MENU\\CSCTRL7A.TIM;1");
	IO_Data c1 = IO_Read("\\MENU\\CSCTRL7B.TIM;1");
	if (g0 == NULL || g1 == NULL || g2 == NULL || c0 == NULL || c1 == NULL)
	{
		if (g0 != NULL) Mem_Free(g0);
		if (g1 != NULL) Mem_Free(g1);
		if (g2 != NULL) Mem_Free(g2);
		if (c0 != NULL) Mem_Free(c0);
		if (c1 != NULL) Mem_Free(c1);
		sprintf(error_msg, "[Menu_UploadCSHQUI] v7 source UI TIM missing");
		ErrorLock();
		return;
	}
	Gfx_LoadTex(&menu_cs_grid_v7[0], g0, GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu_cs_grid_v7[1], g1, GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu_cs_grid_v7[2], g2, GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu_cs_ctrl_v7[0], c0, GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu_cs_ctrl_v7[1], c1, GFX_LOADTEX_FREE);
}

'''
    text = between(text, upload_start, upload_end, upload_code, 'v7 UI upload')

    helper_start = 'static void Menu_CSDrawV6Control(const RECT *src, const RECT *dst)\n{'
    helper_end = 'static void Menu_CSDrawHQForeground(const RECT *dst)\n{'
    helpers = r'''static s32 menu_cs_v7_cursor_main_x = 0;
static s32 menu_cs_v7_cursor_main_y = 0;
static s32 menu_cs_v7_cursor_light_x = 0;
static s32 menu_cs_v7_cursor_light_y = 0;
static s32 menu_cs_v7_cursor_dark_x = 0;
static s32 menu_cs_v7_cursor_dark_y = 0;
static boolean menu_cs_v7_cursor_init = false;

static void Menu_CSDrawV7Control(const RECT *src, const RECT *dst)
{
	if (src->x < 128 && (src->x + src->w) > 128)
	{
		s32 left_w = 128 - src->x;
		s32 right_w = src->w - left_w;
		s32 left_dst_w = ((s32)dst->w * left_w) / src->w;
		RECT left_src = {src->x, src->y, left_w, src->h};
		RECT left_dst = {dst->x, dst->y, left_dst_w, dst->h};
		RECT right_src = {0, src->y, right_w, src->h};
		RECT right_dst = {dst->x + left_dst_w, dst->y, dst->w - left_dst_w, dst->h};
		Gfx_DrawTex(&menu_cs_ctrl_v7[0], &left_src, &left_dst);
		Gfx_DrawTex(&menu_cs_ctrl_v7[1], &right_src, &right_dst);
		return;
	}
	u8 page = (src->x >= 128) ? 1 : 0;
	RECT local = {src->x - (page ? 128 : 0), src->y, src->w, src->h};
	Gfx_DrawTex(&menu_cs_ctrl_v7[page], &local, dst);
}

static void Menu_CSDrawV7GridPages(void)
{
	static const s16 widths[3] = {128, 128, 64};
	static const s16 offsets[3] = {0, 128, 256};
	for (u8 page = 0; page < 3; page++)
	{
		RECT src = {0, 0, widths[page], 240};
		RECT dst = {offsets[page], 0, widths[page], 240};
		Gfx_DrawTex(&menu_cs_grid_v7[page], &src, &dst);
	}
}

static void Menu_CSV7UpdateCursor(s16 tx, s16 ty)
{
	s32 fx = ((s32)tx) << 8;
	s32 fy = ((s32)ty) << 8;
	if (!menu_cs_v7_cursor_init)
	{
		menu_cs_v7_cursor_main_x = menu_cs_v7_cursor_light_x = menu_cs_v7_cursor_dark_x = fx;
		menu_cs_v7_cursor_main_y = menu_cs_v7_cursor_light_y = menu_cs_v7_cursor_dark_y = fy;
		menu_cs_v7_cursor_init = true;
		return;
	}
	// Match CharSelectCursors' 0.1 / 0.202 / 0.404 follow behavior closely
	// with 8-bit fixed-point arithmetic.
	menu_cs_v7_cursor_main_x += ((fx - menu_cs_v7_cursor_main_x) * 26) >> 8;
	menu_cs_v7_cursor_main_y += ((fy - menu_cs_v7_cursor_main_y) * 26) >> 8;
	menu_cs_v7_cursor_light_x += ((menu_cs_v7_cursor_main_x - menu_cs_v7_cursor_light_x) * 52) >> 8;
	menu_cs_v7_cursor_light_y += ((menu_cs_v7_cursor_main_y - menu_cs_v7_cursor_light_y) * 52) >> 8;
	menu_cs_v7_cursor_dark_x += ((fx - menu_cs_v7_cursor_dark_x) * 103) >> 8;
	menu_cs_v7_cursor_dark_y += ((fy - menu_cs_v7_cursor_dark_y) * 103) >> 8;
}

'''
    text = between(text, helper_start, helper_end, helpers, 'v7 UI helpers')

    # The legacy function name is retained because the already-proven live draw
    # block calls it. Its implementation is now native 320x240 8bpp and changes
    # frame at ~7.5fps using genuine official timeline samples.
    draw_bg_start = 'static void Menu_CSDrawHQ16(const RECT *dst)\n{'
    draw_bg_end = 'static void Menu_CSDrawForeground(void)\n{'
    draw_bg = r'''static void Menu_CSDrawHQ16(const RECT *dst)
{
	Menu_SetCSV7BackgroundFrame((u8)((animf_count / 8) % CSV7_BG_FRAME_COUNT));
	static const s16 widths[3] = {128, 128, 64};
	static const s16 offsets[3] = {0, 128, 256};
	for (u8 page = 0; page < 3; page++)
	{
		Gfx_Tex tex;
		tex.tim_mode = 1;
		tex.tpage = getTPage(1, 0, MENU_CS_V7_BG_VRAM_X + page * 64, MENU_CS_V7_BG_VRAM_Y);
		tex.clut = getClut(MENU_CS_V7_BG_CLUT_X, MENU_CS_V7_BG_CLUT_Y);
		tex.pxshift = 1;
		RECT src = {0, 0, widths[page], MENU_CS_HQ_H};
		s32 x0 = dst->x + ((s32)dst->w * offsets[page]) / MENU_CS_HQ_W;
		s32 x1 = dst->x + ((s32)dst->w * (offsets[page] + widths[page])) / MENU_CS_HQ_W;
		RECT part = {x0, dst->y, x1 - x0, dst->h};
		Gfx_DrawTex(&tex, &src, &part);
	}
}

'''
    text = between(text, draw_bg_start, draw_bg_end, draw_bg, 'v7 animated background draw')

    grid_start = 'static void Menu_CSDrawGrid(void)\n{'
    grid_end = 'static void Menu_CSDrawGridLegacy(void)\n{'
    grid_code = r'''static void Menu_CSDrawGrid(void)
{
	u8 state = menu_cs_grid % 9;
	s16 tx = csv7_cursor_x[state];
	s16 ty = csv7_cursor_y[state];
	Menu_CSV7UpdateCursor(tx, ty);

	// PS1 ordering tables are LIFO. Submit from topmost desired visual to
	// bottommost so rendered order becomes:
	// locks -> BF PixelatedIcon -> cursor trail -> nametag.
	RECT name_src;
	RECT name_dst;
	if (state == 4)
	{
		name_src = (RECT){CSV7_NAME_BF_X, CSV7_NAME_BF_Y, CSV7_NAME_BF_W, CSV7_NAME_BF_H};
		name_dst = (RECT){CSV7_NAME_BF_DST_X, CSV7_NAME_BF_DST_Y, CSV7_NAME_BF_W, CSV7_NAME_BF_H};
	}
	else
	{
		name_src = (RECT){CSV7_NAME_LOCKED_X, CSV7_NAME_LOCKED_Y, CSV7_NAME_LOCKED_W, CSV7_NAME_LOCKED_H};
		name_dst = (RECT){CSV7_NAME_LOCKED_DST_X, CSV7_NAME_LOCKED_DST_Y, CSV7_NAME_LOCKED_W, CSV7_NAME_LOCKED_H};
	}
	Menu_CSDrawV7Control(&name_src, &name_dst);

	s16 mx = (s16)(menu_cs_v7_cursor_main_x >> 8);
	s16 my = (s16)(menu_cs_v7_cursor_main_y >> 8);
	s16 lx = (s16)(menu_cs_v7_cursor_light_x >> 8);
	s16 ly = (s16)(menu_cs_v7_cursor_light_y >> 8);
	s16 dx = (s16)(menu_cs_v7_cursor_dark_x >> 8);
	s16 dy = (s16)(menu_cs_v7_cursor_dark_y >> 8);
	if (menu_cs_mode == MenuCS_Confirm)
	{
		RECT src = {CSV7_CURSOR_CONFIRM_X, CSV7_CURSOR_CONFIRM_Y, CSV7_CURSOR_CONFIRM_W, CSV7_CURSOR_CONFIRM_H};
		RECT dst = {mx - 2, my - 4, CSV7_CURSOR_CONFIRM_W, CSV7_CURSOR_CONFIRM_H};
		Menu_CSDrawV7Control(&src, &dst);
	}
	else if (menu_cs_mode == MenuCS_Deny)
	{
		RECT src = {CSV7_CURSOR_DENY_X, CSV7_CURSOR_DENY_Y, CSV7_CURSOR_DENY_W, CSV7_CURSOR_DENY_H};
		RECT dst = {mx - 2, my - 4, CSV7_CURSOR_DENY_W, CSV7_CURSOR_DENY_H};
		Menu_CSDrawV7Control(&src, &dst);
	}
	else
	{
		RECT main_src = ((animf_count >> 3) & 1)
			? (RECT){CSV7_CURSOR_ORANGE_X, CSV7_CURSOR_ORANGE_Y, CSV7_CURSOR_ORANGE_W, CSV7_CURSOR_ORANGE_H}
			: (RECT){CSV7_CURSOR_YELLOW_X, CSV7_CURSOR_YELLOW_Y, CSV7_CURSOR_YELLOW_W, CSV7_CURSOR_YELLOW_H};
		RECT light_src = {CSV7_CURSOR_LIGHT_X, CSV7_CURSOR_LIGHT_Y, CSV7_CURSOR_LIGHT_W, CSV7_CURSOR_LIGHT_H};
		RECT dark_src = {CSV7_CURSOR_DARK_X, CSV7_CURSOR_DARK_Y, CSV7_CURSOR_DARK_W, CSV7_CURSOR_DARK_H};
		RECT main_dst = {mx, my, CSV7_CURSOR_YELLOW_W, CSV7_CURSOR_YELLOW_H};
		RECT light_dst = {lx, ly, CSV7_CURSOR_LIGHT_W, CSV7_CURSOR_LIGHT_H};
		RECT dark_dst = {dx, dy, CSV7_CURSOR_DARK_W, CSV7_CURSOR_DARK_H};
		Menu_CSDrawV7Control(&main_src, &main_dst);
		Menu_CSDrawV7Control(&light_src, &light_dst);
		Menu_CSDrawV7Control(&dark_src, &dark_dst);
	}

	RECT icon_src;
	if (menu_cs_mode == MenuCS_Confirm && state == 4)
		icon_src = (RECT){CSV7_ICON_CONFIRM_X, CSV7_ICON_CONFIRM_Y, CSV7_ICON_CONFIRM_W, CSV7_ICON_CONFIRM_H};
	else
	{
		u8 iframe = (u8)((animf_count / 6) % CSV7_ICON_IDLE_COUNT);
		icon_src = (RECT){csv7_icon_src_x[iframe], csv7_icon_src_y[iframe], csv7_icon_src_w[iframe], csv7_icon_src_h[iframe]};
	}
	RECT icon_dst = (state == 4)
		? (RECT){CSV7_ICON_SEL_X, CSV7_ICON_SEL_Y, CSV7_ICON_SEL_W, CSV7_ICON_SEL_H}
		: (RECT){CSV7_ICON_UNSEL_X, CSV7_ICON_UNSEL_Y, CSV7_ICON_UNSEL_W, CSV7_ICON_UNSEL_H};
	Menu_CSDrawV7Control(&icon_src, &icon_dst);

	Menu_CSDrawV7GridPages();
}

'''
    text = between(text, grid_start, grid_end, grid_code, 'v7 canonical grid renderer')

    # Free the new resident background bank with the other Character Select data.
    free_start = 'static void Menu_FreeCSFrames(void)\n{'
    a = text.find(free_start)
    if a < 0:
        raise SystemExit('v7 free function missing')
    b = text.find('\n}\n', a) + 3
    body = text[a:b]
    insert = '''static void Menu_FreeCSFrames(void)
{
	if (menu_cs_bg_frames != NULL)
	{
		Mem_Free(menu_cs_bg_frames);
		menu_cs_bg_frames = NULL;
	}
'''
    if body.count(free_start) != 1:
        raise SystemExit('v7 free anchor ambiguity')
    body = body.replace(free_start, insert.rstrip('\n'), 1)
    reset = '\tmenu_cs_uploaded_fg_frame = 0xFF;\n'
    if body.count(reset) != 1:
        raise SystemExit(f'v7 free cache reset count {body.count(reset)}')
    body = body.replace(reset, reset + '\tmenu_cs_uploaded_bg_frame = 0xFF;\n', 1)
    text = text[:a] + body + text[b:]

    # Include the background bank in the existing load validity check.
    text = once(
        text,
        'if (menu_cs_frames == NULL || menu_cs_char_frames == NULL || menu_cs_fg_frames == NULL)',
        'if (menu_cs_frames == NULL || menu_cs_char_frames == NULL || menu_cs_fg_frames == NULL || menu_cs_bg_frames == NULL)',
        'v7 load validity check',
    )

    menu_path.write_text(text)

    xml = xml_path.read_text()
    anchor = '\t\t\t\t<file name = "csctrl6b.tim" type = "data" source = "iso/menu/csctrl6b.tim"/>\n'
    if xml.count(anchor) != 1:
        raise SystemExit(f'v7 XML anchor count {xml.count(anchor)}')
    additions = ''.join(
        f'\t\t\t\t<file name = "{name}" type = "data" source = "iso/menu/{name}"/>\n'
        for name in ('csbg7.rle','csgrid7a.tim','csgrid7b.tim','csgrid7c.tim','csctrl7a.tim','csctrl7b.tim')
    )
    xml = xml.replace(anchor, anchor + additions, 1)
    xml_path.write_text(xml)

    low = text.lower()
    required = (
        'charselect_v7_generated.h', 'csbg7.rle;1', 'csgrid7a.tim;1', 'csgrid7b.tim;1',
        'csgrid7c.tim;1', 'csctrl7a.tim;1', 'csctrl7b.tim;1',
        'menu_setcsv7backgroundframe', 'menu_csv7updatecursor', 'csv7_icon_idle_count',
        'menu_cs_hq_char_vram_y 256',
    )
    for marker in required:
        if marker not in low:
            raise SystemExit(f'v7 generated runtime missing {marker}')
    if 'menu_cs_hq_char_vram_x, 0, menu_cs_char_word_w' in low:
        raise SystemExit('font-corrupting v4/v5 character upload returned')
    # Music/XA is deliberately outside this visual patch. Assert the known path
    # still exists rather than silently rebuilding it here.
    if 'charsel.xa;1' not in low:
        raise SystemExit('working Character Select XA route disappeared')

    print('Applied source-correct Character Select v7 visual runtime')


if __name__ == '__main__':
    main()
