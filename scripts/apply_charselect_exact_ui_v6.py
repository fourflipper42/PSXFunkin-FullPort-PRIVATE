#!/usr/bin/env python3
"""Apply the Character Select v6 exact-coordinate UI renderer.

Run after v5/v5.1. The font-safe HQ scene layers remain untouched. Only the
mis-sized hand-fitted selector/grid/nametag path is replaced.
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
        raise SystemExit('usage: apply_charselect_exact_ui_v6.py <upstream>')
    root = Path(sys.argv[1])
    menu_path = root / 'src' / 'menu.c'
    xml_path = root / 'funkin.xml'
    text = menu_path.read_text()

    text = once(
        text,
        '#include "menu.h"\n',
        '#include "menu.h"\n#include "charselect_ui_v6_generated.h"\n',
        'generated header include',
    )

    text = once(
        text,
        'static Gfx_Tex menu_cs_ui_pages[2];\n',
        'static Gfx_Tex menu_cs_grid_v6[3];\nstatic Gfx_Tex menu_cs_ctrl_v6[2];\n',
        'v6 texture declarations',
    )

    upload_start = 'static void Menu_UploadCSHQUI(void)\n{'
    upload_end = 'static void Menu_CSDrawUIRect(const RECT *src, const RECT *dst)\n{'
    new_upload = r'''static void Menu_UploadCSHQUI(void)
{
	IO_Data g0 = IO_Read("\\MENU\\CSGRID6A.TIM;1");
	IO_Data g1 = IO_Read("\\MENU\\CSGRID6B.TIM;1");
	IO_Data g2 = IO_Read("\\MENU\\CSGRID6C.TIM;1");
	IO_Data c0 = IO_Read("\\MENU\\CSCTRL6A.TIM;1");
	IO_Data c1 = IO_Read("\\MENU\\CSCTRL6B.TIM;1");
	if (g0 == NULL || g1 == NULL || g2 == NULL || c0 == NULL || c1 == NULL)
	{
		if (g0 != NULL) Mem_Free(g0);
		if (g1 != NULL) Mem_Free(g1);
		if (g2 != NULL) Mem_Free(g2);
		if (c0 != NULL) Mem_Free(c0);
		if (c1 != NULL) Mem_Free(c1);
		sprintf(error_msg, "[Menu_UploadCSHQUI] v6 exact UI TIM missing");
		ErrorLock();
		return;
	}
	Gfx_LoadTex(&menu_cs_grid_v6[0], g0, GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu_cs_grid_v6[1], g1, GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu_cs_grid_v6[2], g2, GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu_cs_ctrl_v6[0], c0, GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu_cs_ctrl_v6[1], c1, GFX_LOADTEX_FREE);
}

'''
    text = between(text, upload_start, upload_end, new_upload, 'v6 UI upload')

    draw_rect_start = 'static void Menu_CSDrawUIRect(const RECT *src, const RECT *dst)\n{'
    draw_rect_end = 'static void Menu_CSDrawHQForeground(const RECT *dst)\n{'
    new_helpers = r'''static void Menu_CSDrawV6Control(const RECT *src, const RECT *dst)
{
	// 8bpp texture pages are 128 pixels wide. Preserve authentic assets wider
	// than one page (notably the 129px PS1-scaled BF nametag) by splitting the
	// source and destination at the page boundary instead of rescaling it.
	if (src->x < 128 && (src->x + src->w) > 128)
	{
		s32 left_w = 128 - src->x;
		s32 right_w = src->w - left_w;
		s32 left_dst_w = ((s32)dst->w * left_w) / src->w;
		RECT left_src = {src->x, src->y, left_w, src->h};
		RECT left_dst = {dst->x, dst->y, left_dst_w, dst->h};
		RECT right_src = {0, src->y, right_w, src->h};
		RECT right_dst = {dst->x + left_dst_w, dst->y, dst->w - left_dst_w, dst->h};
		Gfx_DrawTex(&menu_cs_ctrl_v6[0], &left_src, &left_dst);
		Gfx_DrawTex(&menu_cs_ctrl_v6[1], &right_src, &right_dst);
		return;
	}

	u8 page = (src->x >= 128) ? 1 : 0;
	RECT local = {src->x - (page ? 128 : 0), src->y, src->w, src->h};
	Gfx_DrawTex(&menu_cs_ctrl_v6[page], &local, dst);
}

static void Menu_CSDrawV6GridPages(void)
{
	static const s16 widths[3] = {128, 128, 64};
	static const s16 offsets[3] = {0, 128, 256};
	for (u8 page = 0; page < 3; page++)
	{
		RECT src = {0, 0, widths[page], 240};
		RECT dst = {offsets[page], 0, widths[page], 240};
		Gfx_DrawTex(&menu_cs_grid_v6[page], &src, &dst);
	}
}

'''
    text = between(text, draw_rect_start, draw_rect_end, new_helpers, 'v6 control draw helpers')

    grid_start = 'static void Menu_CSDrawGrid(void)\n{'
    grid_end = 'static void Menu_CSDrawGridLegacy(void)\n{'
    new_grid = r'''static void Menu_CSDrawGrid(void)
{
	// The entire lock/BF-icon grid is rendered from the official 1280x720
	// source coordinates and downsampled once. No guessed per-cell sizing.
	Menu_CSDrawV6GridPages();

	RECT name_src;
	RECT name_dst;
	if (menu_cs_grid == 4)
	{
		name_src = (RECT){CSV6_NAME_BF_X, CSV6_NAME_BF_Y, CSV6_NAME_BF_W, CSV6_NAME_BF_H};
		name_dst = (RECT){CSV6_NAME_BF_DST_X, CSV6_NAME_BF_DST_Y, CSV6_NAME_BF_W, CSV6_NAME_BF_H};
	}
	else
	{
		name_src = (RECT){CSV6_NAME_LOCKED_X, CSV6_NAME_LOCKED_Y, CSV6_NAME_LOCKED_W, CSV6_NAME_LOCKED_H};
		name_dst = (RECT){CSV6_NAME_LOCKED_DST_X, CSV6_NAME_LOCKED_DST_Y, CSV6_NAME_LOCKED_W, CSV6_NAME_LOCKED_H};
	}
	Menu_CSDrawV6Control(&name_src, &name_dst);

	s16 cx = csv6_cursor_x[menu_cs_grid % 9];
	s16 cy = csv6_cursor_y[menu_cs_grid % 9];

	if (menu_cs_mode == MenuCS_Confirm)
	{
		RECT src = {CSV6_CURSOR_CONFIRM_X, CSV6_CURSOR_CONFIRM_Y, CSV6_CURSOR_CONFIRM_W, CSV6_CURSOR_CONFIRM_H};
		RECT dst = {cx - 1, cy - 1, CSV6_CURSOR_CONFIRM_W, CSV6_CURSOR_CONFIRM_H};
		Menu_CSDrawV6Control(&src, &dst);
	}
	else if (menu_cs_mode == MenuCS_Deny)
	{
		RECT src = {CSV6_CURSOR_DENY_X, CSV6_CURSOR_DENY_Y, CSV6_CURSOR_DENY_W, CSV6_CURSOR_DENY_H};
		RECT dst = {cx - 1, cy - 1, CSV6_CURSOR_DENY_W, CSV6_CURSOR_DENY_H};
		Menu_CSDrawV6Control(&src, &dst);
	}
	else
	{
		RECT dark_src = {CSV6_CURSOR_DARK_X, CSV6_CURSOR_DARK_Y, CSV6_CURSOR_DARK_W, CSV6_CURSOR_DARK_H};
		RECT light_src = {CSV6_CURSOR_LIGHT_X, CSV6_CURSOR_LIGHT_Y, CSV6_CURSOR_LIGHT_W, CSV6_CURSOR_LIGHT_H};
		RECT main_src;
		if ((animf_count >> 3) & 1)
			main_src = (RECT){CSV6_CURSOR_ORANGE_X, CSV6_CURSOR_ORANGE_Y, CSV6_CURSOR_ORANGE_W, CSV6_CURSOR_ORANGE_H};
		else
			main_src = (RECT){CSV6_CURSOR_YELLOW_X, CSV6_CURSOR_YELLOW_Y, CSV6_CURSOR_YELLOW_W, CSV6_CURSOR_YELLOW_H};

		RECT dark_dst = {cx - 4, cy - 2, CSV6_CURSOR_DARK_W, CSV6_CURSOR_DARK_H};
		RECT light_dst = {cx - 2, cy - 1, CSV6_CURSOR_LIGHT_W, CSV6_CURSOR_LIGHT_H};
		RECT main_dst = {cx, cy, CSV6_CURSOR_YELLOW_W, CSV6_CURSOR_YELLOW_H};
		Menu_CSDrawV6Control(&dark_src, &dark_dst);
		Menu_CSDrawV6Control(&light_src, &light_dst);
		Menu_CSDrawV6Control(&main_src, &main_dst);
	}
}

'''
    text = between(text, grid_start, grid_end, new_grid, 'v6 exact grid renderer')
    menu_path.write_text(text)

    xml = xml_path.read_text()
    anchor = '\t\t\t\t<file name = "csui8b.tim" type = "data" source = "iso/menu/csui8b.tim"/>\n'
    if xml.count(anchor) != 1:
        raise SystemExit(f'v6 XML anchor count {xml.count(anchor)}')
    additions = ''.join(
        f'\t\t\t\t<file name = "{name}" type = "data" source = "iso/menu/{name}"/>\n'
        for name in ('csgrid6a.tim', 'csgrid6b.tim', 'csgrid6c.tim', 'csctrl6a.tim', 'csctrl6b.tim')
    )
    xml = xml.replace(anchor, anchor + additions, 1)
    xml_path.write_text(xml)

    low = text.lower()
    for marker in (
        'charselect_ui_v6_generated.h', 'csgrid6a.tim;1', 'csgrid6b.tim;1', 'csgrid6c.tim;1',
        'csctrl6a.tim;1', 'csctrl6b.tim;1', 'menu_csdrawv6gridpages', 'csv6_name_bf_dst_x',
        'csv6_cursor_x[menu_cs_grid % 9]', 'left_w = 128 - src->x',
    ):
        if marker not in low:
            raise SystemExit(f'v6 runtime missing {marker}')

    # Retain the already-confirmed font-safe v5 placements.
    if '#define menu_cs_hq_char_vram_y 256' not in low:
        raise SystemExit('font-safe character VRAM placement was lost')
    if 'menu_cs_hq_char_vram_x, 0, menu_cs_char_word_w' in low:
        raise SystemExit('font-corrupting y=0 character upload returned')

    print('Applied Character Select v6 exact source-coordinate UI renderer with cross-page nametag draws')


if __name__ == '__main__':
    main()
