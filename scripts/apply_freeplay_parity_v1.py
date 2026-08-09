#!/usr/bin/env python3
"""Apply the first full Freeplay parity runtime after Character Select v7.1.

The patch is intentionally isolated to Freeplay. It asserts that the complete
Character Select case is byte-identical before and after the edit.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    begin = text.find(start)
    if begin < 0:
        raise SystemExit(f"{label}: start anchor missing")
    finish = text.find(end, begin + len(start))
    if finish < 0:
        raise SystemExit(f"{label}: end anchor missing")
    return text[:begin] + replacement + text[finish:]


FREEPLAY_DATA = r'''
typedef struct
{
	StageId stage;
	XA_Track preview_track;
	u8 preview_channel;
	const char *text;
	const char *week;
	u16 bpm;
	u16 erect_bpm;
	u8 rating[StageDiff_Max];
	u8 album_cell;
	u8 icon_cell;
} MenuFreeplaySong;

#define MENU_FP_SONG_COUNT 22
#define MENU_FP_OPTION_COUNT (MENU_FP_SONG_COUNT + 1)
#define MENU_FP_RANDOM_OPTION 0
#define MENU_FP_META_CELL 48
#define MENU_FP_META_VRAM_X 512
#define MENU_FP_PREVIEW_DELAY 15
#define MENU_FP_DIGIT_Y 208
#define MENU_FP_DIGIT_W 9
#define MENU_FP_DIGIT_H 14

static const MenuFreeplaySong menu_fp_songs[MENU_FP_SONG_COUNT] = {
	{StageId_1_4, XA_Tutorial, 2, "TUTORIAL", "TUTORIAL", 100, 100, {0,0,1,0,0}, 0, 17},
	{StageId_1_1, XA_Bopeebo, 0, "BOPEEBO", "WEEK 1", 100, 123, {1,1,2,7,8}, 0, 8},
	{StageId_1_2, XA_Fresh, 2, "FRESH", "WEEK 1", 120, 125, {1,1,2,6,7}, 0, 8},
	{StageId_1_3, XA_Dadbattle, 0, "DADBATTLE", "WEEK 1", 180, 190, {1,2,3,9,10}, 0, 8},
	{StageId_2_1, XA_Spookeez, 0, "SPOOKEEZ", "WEEK 2", 150, 166, {1,1,2,11,12}, 0, 9},
	{StageId_2_2, XA_South, 2, "SOUTH", "WEEK 2", 165, 177, {1,2,2,8,9}, 0, 9},
	{StageId_2_3, XA_Monster, 0, "MONSTER", "WEEK 2", 95, 95, {1,2,2,0,0}, 1, 10},
	{StageId_3_1, XA_Pico, 0, "PICO", "WEEK 3", 150, 162, {1,2,2,9,10}, 0, 11},
	{StageId_3_2, XA_Philly, 2, "PHILLY NICE", "WEEK 3", 175, 175, {1,2,3,8,9}, 0, 11},
	{StageId_3_3, XA_Blammed, 0, "BLAMMED", "WEEK 3", 165, 170, {1,2,3,11,12}, 0, 11},
	{StageId_4_1, XA_SatinPanties, 0, "SATIN PANTIES", "WEEK 4", 110, 135, {1,2,2,11,12}, 0, 12},
	{StageId_4_2, XA_High, 2, "HIGH", "WEEK 4", 125, 125, {1,2,3,8,9}, 0, 12},
	{StageId_4_3, XA_MILF, 0, "MILF", "WEEK 4", 180, 180, {2,3,4,0,0}, 0, 12},
	{StageId_5_1, XA_Cocoa, 0, "COCOA", "WEEK 5", 100, 174, {1,2,2,7,8}, 0, 13},
	{StageId_5_2, XA_Eggnog, 2, "EGGNOG", "WEEK 5", 150, 140, {1,2,3,6,7}, 0, 13},
	{StageId_5_3, XA_WinterHorrorland, 0, "WINTER HORRORLAND", "WEEK 5", 159, 159, {1,2,2,0,0}, 1, 10},
	{StageId_6_1, XA_Senpai, 0, "SENPAI", "WEEK 6", 144, 158, {1,2,3,6,7}, 1, 14},
	{StageId_6_2, XA_Roses, 2, "ROSES", "WEEK 6", 120, 128, {2,3,4,8,9}, 1, 14},
	{StageId_6_3, XA_Thorns, 0, "THORNS", "WEEK 6", 190, 190, {2,3,4,9,10}, 1, 15},
	{StageId_7_1, XA_Ugh, 0, "UGH", "WEEK 7", 160, 170, {2,3,4,8,9}, 1, 16},
	{StageId_7_2, XA_Guns, 2, "GUNS", "WEEK 7", 185, 185, {3,4,5,0,0}, 1, 16},
	{StageId_7_3, XA_Stress, 0, "STRESS", "WEEK 7", 178, 178, {3,4,5,0,0}, 1, 16},
};

static Gfx_Tex menu_fp_anim;
static Gfx_Tex menu_fp_meta;
static u8 menu_fp_random_pick = 0;
static u8 menu_fp_preview_song = 0xFF;
static u8 menu_fp_preview_delay = 0;
static u8 menu_fp_art_timer = 0;
static s8 menu_fp_hold_direction = 0;
static u8 menu_fp_hold_frames = 0;
static u32 menu_fp_favorites = 0;

static u8 Menu_FreeplaySongIndex(u8 option)
{
	if (option == MENU_FP_RANDOM_OPTION)
		return menu_fp_random_pick % MENU_FP_SONG_COUNT;
	return (option - 1) % MENU_FP_SONG_COUNT;
}

static const MenuFreeplaySong *Menu_FreeplaySong(u8 option)
{
	return &menu_fp_songs[Menu_FreeplaySongIndex(option)];
}

static void Menu_FreeplaySelectionChanged(void)
{
	if (menu.select == MENU_FP_RANDOM_OPTION)
		menu_fp_random_pick = (u8)RandomRange(0, MENU_FP_SONG_COUNT - 1);
	menu_fp_preview_delay = MENU_FP_PREVIEW_DELAY;
	menu_fp_preview_song = 0xFF;
	menu_fp_art_timer = 0;
	Audio_StopXA();
}

static void Menu_FreeplayTickPreview(void)
{
	u8 song_index = Menu_FreeplaySongIndex(menu.select);
	if (menu_fp_preview_song == song_index)
		return;
	if (menu_fp_preview_delay != 0)
	{
		menu_fp_preview_delay--;
		return;
	}

	const MenuFreeplaySong *song = &menu_fp_songs[song_index];
	CdlFILE preview;
	Audio_GetXAFile(&preview, song->preview_track);
	preview.size = ((preview.size / 5) / IO_SECT_SIZE) * IO_SECT_SIZE;
	if (preview.size < IO_SECT_SIZE)
		preview.size = IO_SECT_SIZE;
	Audio_PlayXA_File(&preview, 0x40, song->preview_channel, true);
	menu_fp_preview_song = song_index;
}

static void Menu_FreeplayDrawMeta(u8 cell, const RECT *dst)
{
	static const u8 column_x[4] = {0, 48, 128, 176};
	u8 column = cell & 3;
	u8 row = cell >> 2;
	RECT src = {column_x[column], row * MENU_FP_META_CELL, MENU_FP_META_CELL, MENU_FP_META_CELL};
	Gfx_Tex tex = menu_fp_meta;
	if (src.x >= 128)
	{
		tex.tpage = getTPage(1, 0, MENU_FP_META_VRAM_X + 64, 0);
		src.x -= 128;
	}
	Gfx_DrawTex(&tex, &src, dst);
}

static void Menu_FreeplayDrawSmallText(const char *text, s16 x, s16 y)
{
	u32 pattern = 0;
	u8 phase = (animf_count >> 1) & 1;
	while (*text != '\0')
	{
		u8 original = (u8)*text++;
		if (original >= 'A' && original <= 'Z')
		{
			u8 c = original - 'A';
			RECT src = {((c & 7) << 5) + ((((pattern >> c) & 1) ^ phase) << 4), (c & ~7) << 1, 16, 16};
			RECT dst = {x, y, 8, 8};
			Gfx_DrawTex(&menu.font_bold.tex, &src, &dst);
			pattern ^= 1u << c;
		}
		x += 7;
	}
}

static s16 Menu_FreeplayDrawNumber(u16 value, s16 x, s16 y, u8 width, u8 height)
{
	u8 digits[5];
	u8 count = 0;
	do
	{
		digits[count++] = value % 10;
		value /= 10;
	} while (value != 0 && count < COUNT_OF(digits));

	while (count != 0)
	{
		u8 digit = digits[--count];
		RECT src = {digit * MENU_FP_DIGIT_W, MENU_FP_DIGIT_Y, MENU_FP_DIGIT_W, MENU_FP_DIGIT_H};
		RECT dst = {x, y, width, height};
		Gfx_DrawTex(&menu_fp_anim, &src, &dst);
		x += width;
	}
	return x;
}

static void Menu_FreeplayMove(s8 direction)
{
	s16 next = (s16)menu.select + direction;
	if (next < 0)
		next = MENU_FP_OPTION_COUNT - 1;
	else if (next >= MENU_FP_OPTION_COUNT)
		next = 0;
	menu.select = (u8)next;
}

'''


FREEPLAY_CASE = r'''		case MenuPage_Freeplay:
		{
			if (menu.page_swap)
			{
				menu.select = menu_freeplay_song;
				if (menu.select >= MENU_FP_OPTION_COUNT)
					menu.select = 0;
				menu.page_param.stage.diff = menu_freeplay_diff;
				menu_fp_hold_direction = 0;
				menu_fp_hold_frames = 0;
				menu.scroll = menu.select * FIXED_DEC(32,1);
				Menu_FreeplaySelectionChanged();
			}

			const MenuFreeplaySong *song = Menu_FreeplaySong(menu.select);
			if (!Stage_SupportsDifficulty(song->stage, menu.page_param.stage.diff))
				menu.page_param.stage.diff = StageDiff_Normal;

			if (menu.next_page == menu.page && Trans_Idle())
			{
				u8 old_select = menu.select;
				s8 pressed_direction = 0;
				if (pad_state.press & PAD_UP)
					pressed_direction = -1;
				else if (pad_state.press & PAD_DOWN)
					pressed_direction = 1;

				if (pressed_direction != 0)
				{
					Menu_FreeplayMove(pressed_direction);
					menu_fp_hold_direction = pressed_direction;
					menu_fp_hold_frames = 0;
				}
				else
				{
					s8 held_direction = (pad_state.held & PAD_UP) ? -1 : ((pad_state.held & PAD_DOWN) ? 1 : 0);
					if (held_direction == 0)
					{
						menu_fp_hold_direction = 0;
						menu_fp_hold_frames = 0;
					}
					else if (held_direction != menu_fp_hold_direction)
					{
						menu_fp_hold_direction = held_direction;
						menu_fp_hold_frames = 0;
					}
					else
					{
						if (menu_fp_hold_frames < 255)
							menu_fp_hold_frames++;
						if (menu_fp_hold_frames >= 54 && ((menu_fp_hold_frames - 54) & 3) == 0)
							Menu_FreeplayMove(held_direction);
					}
				}

				if (pad_state.press & PAD_L1)
				{
					for (u8 i = 0; i < 5; i++) Menu_FreeplayMove(-1);
				}
				if (pad_state.press & PAD_R1)
				{
					for (u8 i = 0; i < 5; i++) Menu_FreeplayMove(1);
				}
				if (pad_state.press & PAD_SELECT)
					menu.select = MENU_FP_RANDOM_OPTION;

				if (menu.select != old_select)
				{
					Menu_FreeplaySelectionChanged();
					song = Menu_FreeplaySong(menu.select);
					if (!Stage_SupportsDifficulty(song->stage, menu.page_param.stage.diff))
						menu.page_param.stage.diff = StageDiff_Normal;
				}

				Menu_V084DifficultyTick(song->stage);

				if ((pad_state.press & PAD_SQUARE) && menu.select != MENU_FP_RANDOM_OPTION)
					menu_fp_favorites ^= (1u << Menu_FreeplaySongIndex(menu.select));

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
						menu.page_param.stage.id = song->stage;
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

				if (menu.next_page == menu.page)
					Menu_FreeplayTickPreview();
			}
			menu_freeplay_diff = menu.page_param.stage.diff;
			if (menu_fp_art_timer < 12)
				menu_fp_art_timer++;

			s32 next_scroll = menu.select * FIXED_DEC(32,1);
			menu.scroll += (next_scroll - menu.scroll) >> 3;

			// Foreground submissions come first because the PS1 ordering table is LIFO.
			Menu_DrawV084Difficulty(244, 24);
			menu.font_bold.draw(&menu.font_bold, "FREEPLAY", 10, 8, FontAlign_Left);
			menu.font_bold.draw(&menu.font_bold,
				(menu.select == MENU_FP_RANDOM_OPTION) ? "ANY SONG" : song->week,
				15, 92, FontAlign_Left);
			Menu_FreeplayDrawSmallText("TRIANGLE CHARACTER", 8, SCREEN_HEIGHT - 10);
			Menu_FreeplayDrawSmallText("SHOULDERS JUMP SELECT RANDOM", 126, SCREEN_HEIGHT - 10);

			u16 shown_bpm = (menu.page_param.stage.diff >= StageDiff_Erect) ? song->erect_bpm : song->bpm;
			u8 shown_rating = song->rating[menu.page_param.stage.diff];
			Menu_FreeplayDrawSmallText("PERSONAL BEST", 150, 42);
			Menu_FreeplayDrawNumber(0, 244, 40, 7, 11);
			Menu_FreeplayDrawSmallText("COMPLETION", 150, 52);
			Menu_FreeplayDrawNumber(0, 224, 50, 7, 11);
			Menu_FreeplayDrawSmallText("PERCENT", 234, 52);
			if (menu.select != MENU_FP_RANDOM_OPTION && (menu_fp_favorites & (1u << Menu_FreeplaySongIndex(menu.select))))
				Menu_FreeplayDrawSmallText("FAVORITE", 264, 42);

			u8 capsule_frame = (u8)((animf_count / 4) & 7);
			u8 selector_frame = (u8)((animf_count / 3) % 15);
			for (u8 option = 0; option < MENU_FP_OPTION_COUNT; option++)
			{
				s32 y = 68 + (option * 32) - (menu.scroll >> FIXED_SHIFT);
				if (y < 36 || y > SCREEN_HEIGHT - 27)
					continue;
				boolean selected = option == menu.select;
				const char *label = (option == MENU_FP_RANDOM_OPTION)
					? "RANDOM"
					: menu_fp_songs[option - 1].text;

				if (selected)
				{
					RECT pointer_src = {
						208 + (selector_frame % 3) * 16,
						(selector_frame / 3) * 30,
						16, 30
					};
					RECT pointer_dst = {128, y - 15, 16, 30};
					Gfx_DrawTex(&menu_fp_anim, &pointer_src, &pointer_dst);
				}

				Menu_FreeplayDrawSmallText(label, selected ? 159 : 166, y - 4);
				if (selected && option != MENU_FP_RANDOM_OPTION)
				{
					RECT bpm_src = {96, MENU_FP_DIGIT_Y, 25, 14};
					RECT bpm_dst = {161, y + 5, 13, 7};
					Gfx_DrawTex(&menu_fp_anim, &bpm_src, &bpm_dst);
					Menu_FreeplayDrawNumber(shown_bpm, 176, y + 4, 5, 8);
					Menu_FreeplayDrawSmallText("RATING", 242, y + 5);
					Menu_FreeplayDrawNumber(shown_rating, 287, y + 4, 5, 8);
				}
				RECT capsule_src = {
					selected ? 0 : 104,
					capsule_frame * 24,
					104, 24
				};
				RECT capsule_dst = {
					selected ? 139 : 149,
					y - (selected ? 14 : 12),
					selected ? 181 : 166,
					selected ? 30 : 26
				};
				Gfx_DrawTex(&menu_fp_anim, &capsule_src, &capsule_dst);
			}

			// All fourteen shipped Boyfriend DJ frames remain at 24 fps.
			u8 dj_frame = (u8)(((animf_count * 2) / 5) % MENU_DJ_FRAME_COUNT);
			Menu_SetDJFrame(dj_frame);
			RECT dj_src = {0, 0, MENU_DJ_FRAME_W, MENU_DJ_FRAME_H};
			RECT dj_dst = {-8, 47, 150, 150};
			Gfx_DrawTex(&menu.tex_title, &dj_src, &dj_dst);

			s16 art_size = 42 + (menu_fp_art_timer >> 1);
			RECT album_dst = {12 + ((48 - art_size) >> 1), 19 + ((48 - art_size) >> 1), art_size, art_size};
			RECT icon_dst = {76, 22, 46, 46};
			Menu_FreeplayDrawMeta(
				(menu.select == MENU_FP_RANDOM_OPTION) ? 0 : song->album_cell,
				&album_dst);
			Menu_FreeplayDrawMeta(
				(menu.select == MENU_FP_RANDOM_OPTION) ? 7 : song->icon_cell,
				&icon_dst);

			RECT bg_src = {0, 0, 256, 192};
			RECT bg_dst = {0, 0, SCREEN_WIDTH, SCREEN_HEIGHT};
			Gfx_DrawTex(&menu.tex_back, &bg_src, &bg_dst);
			break;
		}

'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    menu_path = args.root / "src/menu.c"
    xml_path = args.root / "funkin.xml"
    text = menu_path.read_text()

    if '#include "charselect_v7_1_generated.h"' not in text:
        raise SystemExit("Freeplay parity v1 must run after Character Select v7.1")

    cs_start = text.find("\t\tcase MenuPage_CharacterSelect:")
    cs_end = text.find("\t\tcase MenuPage_Mods:", cs_start)
    if cs_start < 0 or cs_end < 0:
        raise SystemExit("could not isolate frozen Character Select case")
    frozen_character_select = text[cs_start:cs_end]

    text = once(text, '#include "mutil.h"\n', '#include "mutil.h"\n#include "random.h"\n', "random include")
    text = once(
        text,
        "static u8 menu_dj_frame = 0xFF;\n",
        "static u8 menu_dj_frame = 0xFF;\n" + FREEPLAY_DATA,
        "Freeplay data and helpers",
    )
    text = once(
        text,
        "\t\tMenu_LoadDJFrames();\n\t\tMenu_SetDJFrame(0);\n",
        "\t\tMenu_LoadDJFrames();\n"
        "\t\tMenu_SetDJFrame(0);\n"
        "\t\tGfx_LoadTex(&menu_fp_anim, IO_Read(\"\\\\MENU\\\\FPANIM.TIM;1\"), GFX_LOADTEX_FREE);\n"
        "\t\tGfx_LoadTex(&menu_fp_meta, IO_Read(\"\\\\MENU\\\\FPMETA.TIM;1\"), GFX_LOADTEX_FREE);\n",
        "Freeplay texture load",
    )

    old_leave = (
        "\tif (menu_visual_set == MenuVisual_Freeplay && wanted != MenuVisual_Freeplay)\n"
        "\t\tMenu_FreeDJFrames();\n"
    )
    new_leave = (
        "\tif (menu_visual_set == MenuVisual_Freeplay && wanted != MenuVisual_Freeplay)\n"
        "\t{\n"
        "\t\tMenu_FreeDJFrames();\n"
        "\t\tmenu_fp_preview_song = 0xFF;\n"
        "\t\tif (page != MenuPage_Stage && page != MenuPage_CharacterSelect)\n"
        "\t\t{\n"
        "\t\t\tAudio_PlayXA_Track(XA_GettinFreaky, 0x40, 0, true);\n"
        "\t\t\tAudio_WaitPlayXA();\n"
        "\t\t}\n"
        "\t}\n"
    )
    text = once(text, old_leave, new_leave, "Freeplay audio restore")
    text = between(
        text,
        "\t\tcase MenuPage_Freeplay:",
        "\t\tcase MenuPage_CharacterSelect:",
        FREEPLAY_CASE,
        "Freeplay page",
    )

    # Some earlier menu generators preserve indentation on otherwise blank
    # lines. Clean only the newly owned Freeplay region so diff --check is
    # deterministic without touching the frozen Character Select case.
    freeplay_start = text.find("typedef struct\n{\n\tStageId stage;")
    new_cs_start = text.find("\t\tcase MenuPage_CharacterSelect:")
    new_cs_end = text.find("\t\tcase MenuPage_Mods:", new_cs_start)
    if freeplay_start < 0 or new_cs_start < 0:
        raise SystemExit("could not isolate generated Freeplay region")
    freeplay_region = text[freeplay_start:new_cs_start]
    freeplay_region = "".join(
        "\n" if line.endswith("\n") and not line[:-1].strip() else line
        for line in freeplay_region.splitlines(keepends=True)
    )
    text = text[:freeplay_start] + freeplay_region + text[new_cs_start:]
    new_cs_start = text.find("\t\tcase MenuPage_CharacterSelect:")
    new_cs_end = text.find("\t\tcase MenuPage_Mods:", new_cs_start)
    if text[new_cs_start:new_cs_end] != frozen_character_select:
        raise SystemExit("Character Select changed while applying Freeplay parity v1")

    menu_path.write_text(text)

    xml = xml_path.read_text()
    anchor = '\t\t\t\t<file name = "fpdj.bin" type = "data" source = "iso/menu/fpdj.bin"/>\n'
    if xml.count(anchor) != 1:
        raise SystemExit(f"Freeplay XML anchor count {xml.count(anchor)}")
    additions = (
        '\t\t\t\t<file name = "fpanim.tim" type = "data" source = "iso/menu/fpanim.tim"/>\n'
        '\t\t\t\t<file name = "fpmeta.tim" type = "data" source = "iso/menu/fpmeta.tim"/>\n'
    )
    xml_path.write_text(xml.replace(anchor, anchor + additions, 1))

    low = text.lower()
    required = (
        "menu_fp_song_count 22",
        "menu_fp_option_count",
        "menu_freeplaytickpreview",
        "menu_freeplaydrawmeta",
        "fpanim.tim;1",
        "fpmeta.tim;1",
        "pad_select",
        "pad_l1",
        "pad_r1",
        "personal best",
        "menu_freeplaydrawnumber",
        "randomrange",
        "charselect_v7_1_generated.h",
    )
    for marker in required:
        if marker not in low:
            raise SystemExit(f"Freeplay parity v1 runtime missing {marker}")
    if low.count("case menupage_characterselect:") != 1:
        raise SystemExit("Character Select case count changed")
    print("Applied official Freeplay parity v1 runtime; Character Select v7.1 frozen")


if __name__ == "__main__":
    main()
