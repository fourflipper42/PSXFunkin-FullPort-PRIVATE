#!/usr/bin/env python3
"""Apply the authentic v0.8.4 Freeplay/Character Select visual pass.

Run after apply_v084_menu_foundation.py. This patch changes presentation only;
all tested menu navigation/state and stage-routing behavior remains intact.
Every raster used by this pass is produced from existing official v0.8.4 files
by build_v084_menu_visual_assets.py; this script does not invent artwork.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one anchor, found {count}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1))


def replace_between(path: Path, start: str, end: str, replacement: str) -> None:
    text = path.read_text()
    a = text.find(start)
    if a < 0:
        raise SystemExit(f"{path}: start anchor not found: {start!r}")
    b = text.find(end, a + len(start))
    if b < 0:
        raise SystemExit(f"{path}: end anchor not found: {end!r}")
    path.write_text(text[:a] + replacement + text[b:])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    args = ap.parse_args()
    root = args.root
    menu_c = root / "src" / "menu.c"
    xml = root / "funkin.xml"

    # Track which of the three VRAM-compatible menu texture sets is live.
    replace_once(
        menu_c,
        "char menu_text_buffer[0x100];\n",
        "char menu_text_buffer[0x100];\n\n"
        "typedef enum\n"
        "{\n"
        "\tMenuVisual_Base = 0,\n"
        "\tMenuVisual_Freeplay,\n"
        "\tMenuVisual_CharacterSelect,\n"
        "} MenuVisualSet;\n\n"
        "static MenuVisualSet menu_visual_set = MenuVisual_Base;\n",
    )

    # Reuse the exact same four texture objects/VRAM destinations as the legacy
    # menu. This keeps live VRAM usage equivalent to the tested foundation.
    lower_anchor = "static const char *Menu_LowerIf(const char *text, boolean lower)"
    loaders = r'''static void Menu_LoadBaseTextures(void)
{
	IO_Data menu_arc = IO_Read("\\MENU\\MENU.ARC;1");
	Gfx_LoadTex(&menu.tex_back,  Archive_Find(menu_arc, "back.tim"),  0);
	Gfx_LoadTex(&menu.tex_ng,    Archive_Find(menu_arc, "ng.tim"),    0);
	Gfx_LoadTex(&menu.tex_story, Archive_Find(menu_arc, "story.tim"), 0);
	Gfx_LoadTex(&menu.tex_title, Archive_Find(menu_arc, "title.tim"), 0);
	Mem_Free(menu_arc);
	menu_visual_set = MenuVisual_Base;
}

static void Menu_LoadV084Textures(MenuVisualSet set)
{
	const char *back_path;
	const char *ng_path;
	const char *story_path;
	const char *title_path;

	if (set == MenuVisual_Freeplay)
	{
		back_path  = "\\MENU\\FPBG.TIM;1";
		ng_path    = "\\MENU\\FPEXTRA.TIM;1";
		story_path = "\\MENU\\FPUI.TIM;1";
		title_path = "\\MENU\\FPCHAR.TIM;1";
	}
	else
	{
		back_path  = "\\MENU\\CSBG.TIM;1";
		ng_path    = "\\MENU\\CSUI.TIM;1";
		story_path = "\\MENU\\CSCHAR.TIM;1";
		title_path = "\\MENU\\CSLAYER.TIM;1";
	}

	Gfx_LoadTex(&menu.tex_back,  IO_Read(back_path),  GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu.tex_ng,    IO_Read(ng_path),    GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu.tex_story, IO_Read(story_path), GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu.tex_title, IO_Read(title_path), GFX_LOADTEX_FREE);
	menu_visual_set = set;
}

static void Menu_SyncV084Textures(MenuPage page)
{
	MenuVisualSet wanted = MenuVisual_Base;
	if (page == MenuPage_Freeplay)
		wanted = MenuVisual_Freeplay;
	else if (page == MenuPage_CharacterSelect)
		wanted = MenuVisual_CharacterSelect;

	if (wanted == menu_visual_set)
		return;
	if (wanted == MenuVisual_Base)
		Menu_LoadBaseTextures();
	else
		Menu_LoadV084Textures(wanted);
}

static void Menu_V084DifficultyTick(StageId stage_id)
{
	if (!Stage_SupportsDifficulty(stage_id, menu.page_param.stage.diff))
		menu.page_param.stage.diff = StageDiff_Normal;

	if (menu.next_page != menu.page || !Trans_Idle())
		return;
	if (!(pad_state.press & (PAD_LEFT | PAD_RIGHT)))
		return;

	s8 direction = (pad_state.press & PAD_RIGHT) ? 1 : -1;
	StageDiff next = menu.page_param.stage.diff;
	for (u8 attempts = 0; attempts < StageDiff_Max; attempts++)
	{
		s8 value = (s8)next + direction;
		if (value < StageDiff_Easy)
			value = StageDiff_Max - 1;
		else if (value >= StageDiff_Max)
			value = StageDiff_Easy;
		next = (StageDiff)value;
		if (Stage_SupportsDifficulty(stage_id, next))
		{
			menu.page_param.stage.diff = next;
			break;
		}
	}
}

static void Menu_DrawV084Difficulty(s32 x, s32 y)
{
	RECT src;
	switch (menu.page_param.stage.diff)
	{
		case StageDiff_Easy:      src = (RECT){  0, 48, 64, 20}; break;
		case StageDiff_Normal:    src = (RECT){ 64, 48, 64, 20}; break;
		case StageDiff_Hard:      src = (RECT){128, 48, 64, 20}; break;
		case StageDiff_Erect:     src = (RECT){192, 48, 64, 20}; break;
		default:                  src = (RECT){  0, 72, 96, 24}; break;
	}
	RECT dst = {x - (src.w >> 1), y - (src.h >> 1), src.w, src.h};
	Gfx_DrawTex(&menu.tex_story, &src, &dst);

	// Authentic v0.8.4 selector arrow art, mirrored by the PS1 GPU.
	RECT arrow = {200, 0, 32, 32};
	RECT left = {x - (src.w >> 1) - 20, y - 8, 16, 16};
	RECT right = {x + (src.w >> 1) + 20, y - 8, -16, 16};
	Gfx_DrawTex(&menu.tex_story, &arrow, &left);
	Gfx_DrawTex(&menu.tex_story, &arrow, &right);
}

'''
    replace_once(menu_c, lower_anchor, loaders + lower_anchor)

    old_load = '''\t//Load menu assets\n\tIO_Data menu_arc = IO_Read("\\\\MENU\\\\MENU.ARC;1");\n\tGfx_LoadTex(&menu.tex_back,  Archive_Find(menu_arc, "back.tim"),  0);\n\tGfx_LoadTex(&menu.tex_ng,    Archive_Find(menu_arc, "ng.tim"),    0);\n\tGfx_LoadTex(&menu.tex_story, Archive_Find(menu_arc, "story.tim"), 0);\n\tGfx_LoadTex(&menu.tex_title, Archive_Find(menu_arc, "title.tim"), 0);\n\tMem_Free(menu_arc);'''
    replace_once(menu_c, old_load, "\t//Load the legacy/base menu texture set.\n\tMenu_LoadBaseTextures();")

    replace_once(
        menu_c,
        "\t//Tick menu page\n\tMenuPage exec_page;",
        "\t//Swap authentic v0.8.4 visual sets only when entering/leaving those pages.\n"
        "\tif (menu.page_swap)\n"
        "\t\tMenu_SyncV084Textures((MenuPage)menu.page);\n\n"
        "\t//Tick menu page\n\tMenuPage exec_page;",
    )

    parity_cases = r'''		case MenuPage_Freeplay:
		{
			static const struct
			{
				StageId stage;
				const char *text;
				const char *week;
			} menu_options[] = {
				{StageId_1_4, "TUTORIAL", "TUTORIAL"},
				{StageId_1_1, "BOPEEBO", "WEEK 1"},
				{StageId_1_2, "FRESH", "WEEK 1"},
				{StageId_1_3, "DADBATTLE", "WEEK 1"},
				{StageId_2_1, "SPOOKEEZ", "WEEK 2"},
				{StageId_2_2, "SOUTH", "WEEK 2"},
				{StageId_2_3, "MONSTER", "WEEK 2"},
				{StageId_3_1, "PICO", "WEEK 3"},
				{StageId_3_2, "PHILLY NICE", "WEEK 3"},
				{StageId_3_3, "BLAMMED", "WEEK 3"},
				{StageId_4_1, "SATIN PANTIES", "WEEK 4"},
				{StageId_4_2, "HIGH", "WEEK 4"},
				{StageId_4_3, "MILF", "WEEK 4"},
				{StageId_5_1, "COCOA", "WEEK 5"},
				{StageId_5_2, "EGGNOG", "WEEK 5"},
				{StageId_5_3, "WINTER HORRORLAND", "WEEK 5"},
				{StageId_6_1, "SENPAI", "WEEK 6"},
				{StageId_6_2, "ROSES", "WEEK 6"},
				{StageId_6_3, "THORNS", "WEEK 6"},
				{StageId_7_1, "UGH", "WEEK 7"},
				{StageId_7_2, "GUNS", "WEEK 7"},
				{StageId_7_3, "STRESS", "WEEK 7"},
			};

			if (menu.page_swap)
			{
				menu.select = menu_freeplay_song;
				if (menu.select >= COUNT_OF(menu_options)) menu.select = 0;
				menu.page_param.stage.diff = menu_freeplay_diff;
				if (!Stage_SupportsDifficulty(menu_options[menu.select].stage, menu.page_param.stage.diff))
					menu.page_param.stage.diff = StageDiff_Normal;
				menu.scroll = menu.select * FIXED_DEC(32,1);
			}

			if (menu.next_page == menu.page && Trans_Idle())
			{
				if (pad_state.press & PAD_UP)
				{
					if (menu.select > 0) menu.select--; else menu.select = COUNT_OF(menu_options) - 1;
				}
				if (pad_state.press & PAD_DOWN)
				{
					if (menu.select < COUNT_OF(menu_options) - 1) menu.select++; else menu.select = 0;
				}

				Menu_V084DifficultyTick(menu_options[menu.select].stage);

				if (pad_state.press & PAD_TRIANGLE)
				{
					menu_freeplay_song = menu.select;
					menu_freeplay_diff = menu.page_param.stage.diff;
					menu.next_page = MenuPage_CharacterSelect;
					menu.next_select = menu_freeplay_player;
					Trans_Start();
				}

				if (pad_state.press & (PAD_START | PAD_CROSS))
				{
					if (menu_freeplay_player == MenuPlayer_Boyfriend)
					{
						menu_freeplay_song = menu.select;
						menu_freeplay_diff = menu.page_param.stage.diff;
						menu.next_page = MenuPage_Stage;
						menu.page_param.stage.id = menu_options[menu.select].stage;
						menu.page_param.stage.story = false;
						Trans_Start();
					}
				}

				if (pad_state.press & PAD_CIRCLE)
				{
					menu_freeplay_song = menu.select;
					menu_freeplay_diff = menu.page_param.stage.diff;
					menu.next_page = MenuPage_Main;
					menu.next_select = 1;
					Trans_Start();
				}
			}
			menu_freeplay_diff = menu.page_param.stage.diff;

			s32 next_scroll = menu.select * FIXED_DEC(32,1);
			menu.scroll += (next_scroll - menu.scroll) >> 3;

			// Submit foreground first because the PS1 OT draws later submissions behind it.
			menu.font_bold.draw(&menu.font_bold, "FREEPLAY", 10, 8, FontAlign_Left);
			menu.font_bold.draw(&menu.font_bold, menu_options[menu.select].week, 15, 92, FontAlign_Left);
			menu.font_bold.draw(&menu.font_bold, "TRIANGLE CHARACTER", 8, SCREEN_HEIGHT - 18, FontAlign_Left);

			for (u8 i = 0; i < COUNT_OF(menu_options); i++)
			{
				s32 y = 66 + (i * 32) - (menu.scroll >> FIXED_SHIFT);
				if (y < 34 || y > SCREEN_HEIGHT - 28) continue;
				boolean selected = i == menu.select;
				s32 cap_x = selected ? 133 : 143;
				s32 cap_w = selected ? 182 : 168;
				menu.font_bold.draw(&menu.font_bold, menu_options[i].text,
					selected ? 159 : 166, y - 5, FontAlign_Left);
				RECT cap_src = {0, 0, 192, 36};
				RECT cap_dst = {cap_x, y - 13, cap_w, selected ? 32 : 28};
				Gfx_DrawTex(&menu.tex_story, &cap_src, &cap_dst);
			}

			Menu_DrawV084Difficulty(244, 24);

			// Authentic BF chill art and Volume 1 album source art.
			RECT bf_src = {0, 0, 128, 192};
			RECT bf_dst = {-2, 38, 130, 192};
			Gfx_DrawTex(&menu.tex_title, &bf_src, &bf_dst);
			RECT album_src = {144, 8, 96, 96};
			RECT album_dst = {12, 20, 70, 70};
			Gfx_DrawTex(&menu.tex_title, &album_src, &album_dst);
			RECT icon_src = {144, 120, 72, 64};
			RECT icon_dst = {75, 20, 54, 48};
			Gfx_DrawTex(&menu.tex_title, &icon_src, &icon_dst);

			// Exact official BF Freeplay background, converted to the original menu VRAM slot.
			RECT bg_src = {0, 0, 256, 192};
			RECT bg_dst = {0, 0, SCREEN_WIDTH, SCREEN_HEIGHT};
			Gfx_DrawTex(&menu.tex_back, &bg_src, &bg_dst);
			break;
		}

		case MenuPage_CharacterSelect:
		{
			if (menu.page_swap)
			{
				menu.select = menu_freeplay_player;
				menu.scroll = menu.select * FIXED_DEC(112,1);
			}

			if (menu.next_page == menu.page && Trans_Idle())
			{
				if (pad_state.press & PAD_LEFT)
				{
					if (menu.select > 0) menu.select--; else menu.select = MenuPlayer_Max - 1;
				}
				if (pad_state.press & PAD_RIGHT)
				{
					if (menu.select < MenuPlayer_Max - 1) menu.select++; else menu.select = 0;
				}
				if (pad_state.press & (PAD_START | PAD_CROSS))
				{
					if (menu.select == MenuPlayer_Boyfriend)
					{
						menu_freeplay_player = MenuPlayer_Boyfriend;
						menu.next_page = MenuPage_Freeplay;
						menu.next_select = menu_freeplay_song;
						Trans_Start();
					}
				}
				if (pad_state.press & (PAD_CIRCLE | PAD_TRIANGLE))
				{
					menu.next_page = MenuPage_Freeplay;
					menu.next_select = menu_freeplay_song;
					Trans_Start();
				}
			}

			// Foreground UI: official selector, icons, nametags, and lock art.
			RECT selector_src = {0, 98, 32, 28};
			RECT selector_dst = {(menu.select == 0) ? 20 : 72, 31, 44, 39};
			Gfx_DrawTex(&menu.tex_ng, &selector_src, &selector_dst);
			RECT bf_icon_src = {36, 0, 40, 36};
			RECT bf_icon_dst = {24, 34, 38, 34};
			Gfx_DrawTex(&menu.tex_ng, &bf_icon_src, &bf_icon_dst);
			RECT pico_icon_src = {78, 0, 48, 36};
			RECT pico_icon_dst = {76, 34, 46, 34};
			Gfx_DrawTex(&menu.tex_ng, &pico_icon_src, &pico_icon_dst);

			if (menu.select == MenuPlayer_Boyfriend)
			{
				RECT tag_src = {0, 68, 80, 26};
				RECT tag_dst = {184, 196, 126, 35};
				Gfx_DrawTex(&menu.tex_ng, &tag_src, &tag_dst);
			}
			else
			{
				RECT tag_src = {80, 68, 48, 28};
				RECT tag_dst = {214, 198, 90, 34};
				Gfx_DrawTex(&menu.tex_ng, &tag_src, &tag_dst);
				RECT lock_src = {40, 98, 24, 24};
				RECT lock_dst = {278, 155, 30, 30};
				Gfx_DrawTex(&menu.tex_ng, &lock_src, &lock_dst);
			}

			// Authentic BF/Pico chill source art. Pico is visible but remains locked
			// functionally until the dedicated Pico Mix checkpoint.
			RECT char_src = {(menu.select == 0) ? 0 : 128, 0, 128, 128};
			RECT char_dst = {150, 54, 150, 166};
			Gfx_DrawTex(&menu.tex_story, &char_src, &char_dst);

			// Official curtains are foreground, so submit before the stage/background.
			RECT curtain_src = {0, 154, 256, 91};
			RECT curtain_dst = {0, 0, SCREEN_WIDTH, 114};
			Gfx_DrawTex(&menu.tex_title, &curtain_src, &curtain_dst);
			RECT stage_src = {0, 0, 256, 142};
			RECT stage_dst = {0, 58, SCREEN_WIDTH, 178};
			Gfx_DrawTex(&menu.tex_title, &stage_src, &stage_dst);

			RECT bg_src = {0, 0, 256, 192};
			RECT bg_dst = {0, 0, SCREEN_WIDTH, SCREEN_HEIGHT};
			Gfx_DrawTex(&menu.tex_back, &bg_src, &bg_dst);
			break;
		}
'''
    replace_between(menu_c, "\t\tcase MenuPage_Freeplay:", "\t\tcase MenuPage_Mods:", parity_cases)

    # Add page-specific authentic TIMs to the disc menu directory.
    replace_once(
        xml,
        '\t\t\t\t<file name = "menu.arc" type = "data" source = "iso/menu/menu.arc"/>\n\t\t\t</dir>',
        '\t\t\t\t<file name = "menu.arc" type = "data" source = "iso/menu/menu.arc"/>\n'
        '\t\t\t\t<file name = "fpbg.tim" type = "data" source = "iso/menu/fpbg.tim"/>\n'
        '\t\t\t\t<file name = "fpchar.tim" type = "data" source = "iso/menu/fpchar.tim"/>\n'
        '\t\t\t\t<file name = "fpui.tim" type = "data" source = "iso/menu/fpui.tim"/>\n'
        '\t\t\t\t<file name = "fpextra.tim" type = "data" source = "iso/menu/fpextra.tim"/>\n'
        '\t\t\t\t<file name = "csbg.tim" type = "data" source = "iso/menu/csbg.tim"/>\n'
        '\t\t\t\t<file name = "cslayer.tim" type = "data" source = "iso/menu/cslayer.tim"/>\n'
        '\t\t\t\t<file name = "cschar.tim" type = "data" source = "iso/menu/cschar.tim"/>\n'
        '\t\t\t\t<file name = "csui.tim" type = "data" source = "iso/menu/csui.tim"/>\n'
        '\t\t\t</dir>',
    )

    # Static guards: no functional Pico enablement or later-content leakage.
    text = menu_c.read_text()
    for required in [
        "Menu_LoadV084Textures", "Menu_SyncV084Textures", "Menu_V084DifficultyTick",
        "FPBG.TIM", "CSBG.TIM", "MenuPlayer_Boyfriend", "MenuPlayer_Pico",
    ]:
        if required not in text:
            raise SystemExit(f"menu parity patch missing {required}")
    if "StageId_8_" in text or "SPAGHETTI" in text:
        raise SystemExit("later milestone content leaked into menu visual checkpoint")

    print("Applied authentic v0.8.4 menu visual parity patch")


if __name__ == "__main__":
    main()
