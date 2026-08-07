#!/usr/bin/env python3
"""Replace the temporary Character Select fallback with the full v0.8.4 PS1 port.

Run after apply_v084_menu_visual_parity.py and fix_v084_menu_visual_feedback.py.
The builder provides authentic v0.8.4 scene/video frames in CSANIM.BIN; this
patch adds the RAM/VRAM streaming runtime, 3x3 wrapped selector, cursor trails,
locked/confirm/deny states, first-entry intro and stayFunky menu music.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:160]!r}")
    path.write_text(text.replace(old, new, 1))


def replace_between(path: Path, start: str, end: str, replacement: str) -> None:
    text = path.read_text()
    a = text.find(start)
    if a < 0:
        raise SystemExit(f"{path}: missing start anchor {start!r}")
    b = text.find(end, a + len(start))
    if b < 0:
        raise SystemExit(f"{path}: missing end anchor {end!r}")
    path.write_text(text[:a] + replacement + text[b:])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    args = ap.parse_args()
    root = args.root
    menu = root / "src/menu.c"
    xml = root / "funkin.xml"

    replace_once(menu, '#include "menu.h"\n', '#include "menu.h"\n#include "charselect_sfx_generated.h"\n')

    globals_block = r'''
#define MENU_CS_FRAME_W 160
#define MENU_CS_FRAME_H 120
#define MENU_CS_FRAME_WORD_W (MENU_CS_FRAME_W / 4)
#define MENU_CS_CLUT_BYTES 32
#define MENU_CS_PIXEL_BYTES (MENU_CS_FRAME_W * MENU_CS_FRAME_H / 2)
#define MENU_CS_RECORD_BYTES (MENU_CS_CLUT_BYTES + MENU_CS_PIXEL_BYTES)
#define MENU_CS_INTRO_FIRST 0
#define MENU_CS_INTRO_COUNT 24
#define MENU_CS_IDLE_FIRST 24
#define MENU_CS_IDLE_COUNT 12
#define MENU_CS_LOCKED_FIRST 36
#define MENU_CS_LOCKED_COUNT 6
#define MENU_CS_CONFIRM_FIRST 42
#define MENU_CS_CONFIRM_COUNT 8
#define MENU_CS_DENY_FIRST 50
#define MENU_CS_DENY_COUNT 4
#define MENU_CS_FRAME_COUNT 54

typedef enum
{
	MenuCS_Intro = 0,
	MenuCS_Live,
	MenuCS_Confirm,
	MenuCS_Deny,
} MenuCSMode;

static IO_Data menu_cs_frames = NULL;
static u8 menu_cs_uploaded_frame = 0xFF;
static MenuCSMode menu_cs_mode = MenuCS_Live;
static u8 menu_cs_grid = 4;
static s8 menu_cs_x = 0;
static s8 menu_cs_y = 0;
static u16 menu_cs_timer = 0;
static boolean menu_cs_seen_intro = false;
static fixed_t menu_cs_cursor_x = 0;
static fixed_t menu_cs_cursor_y = 0;
static fixed_t menu_cs_light_x = 0;
static fixed_t menu_cs_light_y = 0;
static fixed_t menu_cs_dark_x = 0;
static fixed_t menu_cs_dark_y = 0;
'''
    replace_once(
        menu,
        "static u8 menu_dj_frame = 0xFF;\n",
        "static u8 menu_dj_frame = 0xFF;\n" + globals_block,
    )

    helpers = r'''static void Menu_FreeCSFrames(void)
{
	if (menu_cs_frames != NULL)
	{
		Mem_Free(menu_cs_frames);
		menu_cs_frames = NULL;
	}
	menu_cs_uploaded_frame = 0xFF;
}

static void Menu_LoadCSFrames(void)
{
	Menu_FreeCSFrames();
	menu_cs_frames = IO_Read("\\MENU\\CSANIM.BIN;1");
	if (menu_cs_frames == NULL)
	{
		sprintf(error_msg, "[Menu_LoadCSFrames] CSANIM.BIN missing");
		ErrorLock();
	}
	menu_cs_uploaded_frame = 0xFF;
}

static void Menu_SetCSFrame(u8 frame)
{
	if (menu_cs_frames == NULL)
		return;
	frame %= MENU_CS_FRAME_COUNT;
	if (frame == menu_cs_uploaded_frame)
		return;

	u8 *record = (u8*)menu_cs_frames + ((u32)frame * MENU_CS_RECORD_BYTES);
	RECT clut_upload = {
		menu.tex_back.tim_crect.x,
		menu.tex_back.tim_crect.y,
		16,
		1,
	};
	RECT image_upload = {
		menu.tex_back.tim_prect.x,
		menu.tex_back.tim_prect.y,
		MENU_CS_FRAME_WORD_W,
		MENU_CS_FRAME_H,
	};
	LoadImage(&clut_upload, (u32*)record);
	LoadImage(&image_upload, (u32*)(record + MENU_CS_CLUT_BYTES));
	DrawSync(0);
	menu_cs_uploaded_frame = frame;
}

static void Menu_LoadCSSfx(void)
{
	IO_Data bank = IO_Read("\\MENU\\CSSFX.BIN;1");
	if (bank == NULL)
	{
		sprintf(error_msg, "[Menu_LoadCSSfx] CSSFX.BIN missing");
		ErrorLock();
	}
	SpuSetTransferMode(SPU_TRANSFER_BY_IO);
	SpuSetTransferStartAddr(MENU_CS_SFX_SPU_ADDR);
	SpuWrite((u8*)bank, MENU_CS_SFX_BYTES);
	Mem_Free(bank);

	SpuSetKey(SPU_OFF, (u32)1 << 23);
	SpuSetVoiceVolume(23, 0x3000, 0x3000);
	SpuSetVoicePitch(23, MENU_CS_SFX_PITCH);
	SpuSetVoiceADSR(23, 0x7F, 0, 0, 0x1F, 0xF);
}

static void Menu_PlayCSSfx(u32 offset)
{
	SpuSetKey(SPU_OFF, (u32)1 << 23);
	SpuSetVoiceStartAddr(23, MENU_CS_SFX_SPU_ADDR + offset);
	SpuSetKey(SPU_ON, (u32)1 << 23);
}

static void Menu_StartCSMusic(void)
{
	Audio_StopXA();
	Audio_PlayXA("\\MUSIC\\CHARSEL.XA;1", 0x40, 0, 1);
	Audio_WaitPlayXA();
}

static void Menu_RestoreMenuMusic(void)
{
	Audio_StopXA();
	Audio_PlayXA_Track(XA_GettinFreaky, 0x40, 0, 1);
	Audio_WaitPlayXA();
}

static u8 Menu_CSGridIndex(void)
{
	return (u8)((menu_cs_x + 1) + ((menu_cs_y + 1) * 3));
}

static void Menu_CSCursorTarget(fixed_t *x, fixed_t *y)
{
	// Official state uses a 3x3 grid with 110x127 desktop spacing. These are the
	// same relative positions scaled into the PS1 320x240 4:3 presentation.
	*x = FIXED_DEC(95 + ((menu_cs_x + 1) * 43), 1);
	*y = FIXED_DEC(54 + ((menu_cs_y + 1) * 45), 1);
}

static void Menu_CSSnapCursor(void)
{
	Menu_CSCursorTarget(&menu_cs_cursor_x, &menu_cs_cursor_y);
	menu_cs_light_x = menu_cs_cursor_x;
	menu_cs_light_y = menu_cs_cursor_y;
	menu_cs_dark_x = menu_cs_cursor_x;
	menu_cs_dark_y = menu_cs_cursor_y;
}

static void Menu_CSTickCursor(void)
{
	fixed_t tx, ty;
	Menu_CSCursorTarget(&tx, &ty);
	menu_cs_cursor_x += (tx - menu_cs_cursor_x) >> 2;
	menu_cs_cursor_y += (ty - menu_cs_cursor_y) >> 2;
	menu_cs_light_x += (menu_cs_cursor_x - menu_cs_light_x) >> 3;
	menu_cs_light_y += (menu_cs_cursor_y - menu_cs_light_y) >> 3;
	menu_cs_dark_x += (tx - menu_cs_dark_x) >> 4;
	menu_cs_dark_y += (ty - menu_cs_dark_y) >> 4;
}

static void Menu_CSDrawLock(u8 index, s32 x, s32 y)
{
	static const u8 tint[9][3] = {
		{0x19,0x79,0x53}, {0x10,0x76,0x67}, {0x12,0x6D,0x74},
		{0x10,0x76,0x67}, {0x10,0x64,0x6A}, {0x10,0x4E,0x6F},
		{0x10,0x4E,0x6F}, {0x12,0x31,0x65}, {0x12,0x20,0x5D},
	};
	RECT src = {0, 40, 24, 24};
	RECT dst = {x, y, 26, 26};
	Gfx_DrawTexCol(&menu.tex_ng, &src, &dst,
		tint[index][0], tint[index][1], tint[index][2]);
}

static void Menu_CSDrawGrid(void)
{
	for (u8 i = 0; i < 9; i++)
	{
		s32 col = i % 3;
		s32 row = i / 3;
		s32 x = 106 + col * 43;
		s32 y = 62 + row * 45;
		if (i == 4)
		{
			RECT src = {0, 0, 40, 36};
			RECT dst = {x - 7, y - 6, 38, 34};
			Gfx_DrawTex(&menu.tex_ng, &src, &dst);
		}
		else
		{
			Menu_CSDrawLock(i, x, y);
		}
	}
}

static void Menu_CSDrawCursorLayer(fixed_t fx, fixed_t fy, u8 r, u8 g, u8 b, s32 expand)
{
	RECT src = {92, 0, 32, 28};
	s32 x = (fx >> FIXED_SHIFT) - 13 - expand;
	s32 y = (fy >> FIXED_SHIFT) - 11 - expand;
	RECT dst = {x, y, 39 + (expand << 1), 35 + (expand << 1)};
	Gfx_DrawTexCol(&menu.tex_ng, &src, &dst, r, g, b);
}

static void Menu_CSDrawForeground(void)
{
	// Submit foreground before the background: PSXFunkin's current OT bucket is LIFO.
	if (menu_cs_mode == MenuCS_Confirm)
	{
		RECT src = {48, 68, 32, 28};
		RECT dst = {(menu_cs_cursor_x >> FIXED_SHIFT) - 16, (menu_cs_cursor_y >> FIXED_SHIFT) - 14, 48, 42};
		Gfx_DrawTex(&menu.tex_ng, &src, &dst);
	}
	else if (menu_cs_mode == MenuCS_Deny)
	{
		RECT src = {80, 68, 32, 28};
		RECT dst = {(menu_cs_cursor_x >> FIXED_SHIFT) - 16, (menu_cs_cursor_y >> FIXED_SHIFT) - 14, 48, 42};
		Gfx_DrawTex(&menu.tex_ng, &src, &dst);
	}
	else
	{
		Menu_CSDrawCursorLayer(menu_cs_dark_x, menu_cs_dark_y, 0x1E, 0x3A, 0x7C, 0);
		Menu_CSDrawCursorLayer(menu_cs_light_x, menu_cs_light_y, 0x1F, 0x5D, 0x80, 0);
		u8 pulse = (animf_count & 8) ? 0x80 : 0x70;
		Menu_CSDrawCursorLayer(menu_cs_cursor_x, menu_cs_cursor_y, pulse, 0x66, 0x00, 1);
	}

	Menu_CSDrawGrid();

	if (menu_cs_grid == 4)
	{
		RECT tag_src = {24, 40, 80, 26};
		RECT tag_dst = {171, 199, 132, 35};
		Gfx_DrawTex(&menu.tex_ng, &tag_src, &tag_dst);
	}
	else
	{
		RECT tag_src = {0, 68, 48, 28};
		RECT tag_dst = {211, 200, 86, 34};
		Gfx_DrawTex(&menu.tex_ng, &tag_src, &tag_dst);
	}
}

'''
    replace_once(menu, "static void Menu_LoadBaseTextures(void)\n{\n", helpers + "static void Menu_LoadBaseTextures(void)\n{\n")

    # Add the Character Select bank to the existing page-specific load path.
    replace_once(
        menu,
        "\tif (set == MenuVisual_Freeplay)\n\t{\n\t\tMenu_LoadDJFrames();\n\t\tMenu_SetDJFrame(0);\n\t}\n\tmenu_visual_set = set;",
        "\tif (set == MenuVisual_Freeplay)\n"
        "\t{\n\t\tMenu_LoadDJFrames();\n\t\tMenu_SetDJFrame(0);\n\t}\n"
        "\telse if (set == MenuVisual_CharacterSelect)\n"
        "\t{\n\t\tMenu_LoadCSFrames();\n\t\tMenu_LoadCSSfx();\n\t\tMenu_SetCSFrame(MENU_CS_IDLE_FIRST);\n\t}\n"
        "\tmenu_visual_set = set;",
    )
    replace_once(
        menu,
        "\tif (menu_visual_set == MenuVisual_Freeplay && wanted != MenuVisual_Freeplay)\n\t\tMenu_FreeDJFrames();\n\tif (wanted == MenuVisual_Base)",
        "\tif (menu_visual_set == MenuVisual_Freeplay && wanted != MenuVisual_Freeplay)\n\t\tMenu_FreeDJFrames();\n"
        "\tif (menu_visual_set == MenuVisual_CharacterSelect && wanted != MenuVisual_CharacterSelect)\n"
        "\t{\n\t\tMenu_FreeCSFrames();\n\t\tMenu_RestoreMenuMusic();\n\t}\n"
        "\tif (wanted == MenuVisual_Base)",
    )
    replace_once(
        menu,
        "void Menu_Unload(void)\n{\n\tMenu_FreeDJFrames();",
        "void Menu_Unload(void)\n{\n\tMenu_FreeCSFrames();\n\tMenu_FreeDJFrames();",
    )

    character_case = r'''		case MenuPage_CharacterSelect:
		{
			if (menu.page_swap)
			{
				menu.select = menu_freeplay_player;
				menu_cs_x = 0;
				menu_cs_y = 0;
				menu_cs_grid = 4;
				menu_cs_timer = 0;
				Menu_CSSnapCursor();
				if (menu_cs_seen_intro)
				{
					menu_cs_mode = MenuCS_Live;
					Menu_SetCSFrame(MENU_CS_IDLE_FIRST);
					Menu_StartCSMusic();
				}
				else
				{
					menu_cs_mode = MenuCS_Intro;
					Audio_StopXA();
					Menu_SetCSFrame(MENU_CS_INTRO_FIRST);
				}
			}

			menu_cs_timer++;

			if (menu_cs_mode == MenuCS_Intro)
			{
				u8 intro_frame = MENU_CS_INTRO_FIRST + (u8)(((u32)menu_cs_timer * MENU_CS_INTRO_COUNT) / MENU_CS_INTRO_TICKS);
				if (intro_frame >= MENU_CS_INTRO_FIRST + MENU_CS_INTRO_COUNT)
					intro_frame = MENU_CS_INTRO_FIRST + MENU_CS_INTRO_COUNT - 1;
				Menu_SetCSFrame(intro_frame);
				if (menu_cs_timer >= MENU_CS_INTRO_TICKS)
				{
					menu_cs_seen_intro = true;
					menu_cs_mode = MenuCS_Live;
					menu_cs_timer = 0;
					Menu_SetCSFrame(MENU_CS_IDLE_FIRST);
					Menu_PlayCSSfx(MENU_CS_SFX_LIGHTS_OFFSET);
					Menu_StartCSMusic();
				}
			}
			else if (menu_cs_mode == MenuCS_Live)
			{
				if (menu.next_page == menu.page && Trans_Idle())
				{
					boolean moved = false;
					if (pad_state.press & PAD_LEFT)
					{
						menu_cs_x--;
						if (menu_cs_x < -1) menu_cs_x = 1;
						moved = true;
					}
					if (pad_state.press & PAD_RIGHT)
					{
						menu_cs_x++;
						if (menu_cs_x > 1) menu_cs_x = -1;
						moved = true;
					}
					if (pad_state.press & PAD_UP)
					{
						menu_cs_y--;
						if (menu_cs_y < -1) menu_cs_y = 1;
						moved = true;
					}
					if (pad_state.press & PAD_DOWN)
					{
						menu_cs_y++;
						if (menu_cs_y > 1) menu_cs_y = -1;
						moved = true;
					}
					if (moved)
					{
						menu_cs_grid = Menu_CSGridIndex();
						menu_cs_timer = 0;
						Menu_PlayCSSfx(MENU_CS_SFX_SELECT_OFFSET);
					}

					if (pad_state.press & (PAD_START | PAD_CROSS))
					{
						menu_cs_timer = 0;
						if (menu_cs_grid == 4)
						{
							menu_cs_mode = MenuCS_Confirm;
							Menu_PlayCSSfx(MENU_CS_SFX_CONFIRM_OFFSET);
						}
						else
						{
							menu_cs_mode = MenuCS_Deny;
							Menu_PlayCSSfx(MENU_CS_SFX_LOCKED_OFFSET);
						}
					}

					if (pad_state.press & (PAD_CIRCLE | PAD_TRIANGLE))
					{
						menu.next_page = MenuPage_Freeplay;
						menu.next_select = menu_freeplay_song;
						Trans_Start();
					}
				}

				Menu_CSTickCursor();
				if (menu_cs_grid == 4)
					Menu_SetCSFrame(MENU_CS_IDLE_FIRST + (u8)(((animf_count * 2) / 5) % MENU_CS_IDLE_COUNT));
				else
					Menu_SetCSFrame(MENU_CS_LOCKED_FIRST + (u8)(((animf_count * 2) / 5) % MENU_CS_LOCKED_COUNT));
			}
			else if (menu_cs_mode == MenuCS_Confirm)
			{
				Menu_CSTickCursor();
				u8 frame = MENU_CS_CONFIRM_FIRST + (u8)((menu_cs_timer * MENU_CS_CONFIRM_COUNT) / 90);
				if (frame >= MENU_CS_CONFIRM_FIRST + MENU_CS_CONFIRM_COUNT)
					frame = MENU_CS_CONFIRM_FIRST + MENU_CS_CONFIRM_COUNT - 1;
				Menu_SetCSFrame(frame);

				if (pad_state.press & PAD_CIRCLE)
				{
					menu_cs_mode = MenuCS_Live;
					menu_cs_timer = 0;
				}
				else if (menu_cs_timer >= 90)
				{
					menu_freeplay_player = MenuPlayer_Boyfriend;
					menu.next_page = MenuPage_Freeplay;
					menu.next_select = menu_freeplay_song;
					Trans_Start();
				}
			}
			else
			{
				Menu_CSTickCursor();
				u8 deny_frame = MENU_CS_DENY_FIRST + (menu_cs_timer / 3);
				if (deny_frame >= MENU_CS_DENY_FIRST + MENU_CS_DENY_COUNT)
					deny_frame = MENU_CS_DENY_FIRST + MENU_CS_DENY_COUNT - 1;
				Menu_SetCSFrame(deny_frame);
				if (menu_cs_timer >= MENU_CS_DENY_COUNT * 3)
				{
					menu_cs_mode = MenuCS_Live;
					menu_cs_timer = 0;
				}
			}

			if (menu_cs_mode != MenuCS_Intro)
				Menu_CSDrawForeground();

			// The authentic desktop state follows the cursor by about 10 px. The
			// PS1 frame is rendered slightly oversized so this camera shift never
			// exposes an empty border.
			RECT scene_src = {0, 0, MENU_CS_FRAME_W, MENU_CS_FRAME_H};
			RECT scene_dst;
			if (menu_cs_mode == MenuCS_Intro)
				scene_dst = (RECT){0, 0, SCREEN_WIDTH, SCREEN_HEIGHT};
			else
				scene_dst = (RECT){-6 - menu_cs_x * 3, -4 - menu_cs_y * 2, SCREEN_WIDTH + 12, SCREEN_HEIGHT + 8};
			Gfx_DrawTex(&menu.tex_back, &scene_src, &scene_dst);
			break;
		}
'''
    replace_between(menu, "\t\tcase MenuPage_CharacterSelect:", "\t\tcase MenuPage_Mods:", character_case)

    # Disc entries. The scene bank lives beside the other menu files; stayFunky
    # is a standalone XA so it can loop without altering the shared menu XA.
    replace_once(
        xml,
        '\t\t\t\t<file name = "csui.tim" type = "data" source = "iso/menu/csui.tim"/>\n',
        '\t\t\t\t<file name = "csui.tim" type = "data" source = "iso/menu/csui.tim"/>\n'
        '\t\t\t\t<file name = "csanim.bin" type = "data" source = "iso/menu/csanim.bin"/>\n'
        '\t\t\t\t<file name = "cssfx.bin" type = "data" source = "iso/menu/cssfx.bin"/>\n',
    )
    replace_once(
        xml,
        '\t\t\t\t<file name = "menu.xa" type = "xa" source = "iso/music/menu.xa"/>\n',
        '\t\t\t\t<file name = "menu.xa" type = "xa" source = "iso/music/menu.xa"/>\n'
        '\t\t\t\t<file name = "charsel.xa" type = "xa" source = "iso/music/charsel.xa"/>\n'
        '\t\t\t\t<dummy sectors="32"/>\n',
    )

    text = menu.read_text()
    required = [
        "MENU_CS_FRAME_COUNT 54", "CSANIM.BIN", "CSSFX.BIN", "CHARSEL.XA", "Menu_CSGridIndex",
        "Menu_CSDrawGrid", "MenuCS_Intro", "MenuCS_Confirm", "MenuCS_Deny",
        "menu_cs_seen_intro", "MENU_CS_CONFIRM_FIRST", "MENU_CS_DENY_FIRST",
    ]
    for marker in required:
        if marker not in text:
            raise SystemExit(f"Character Select runtime missing {marker}")
    forbidden = ["RECT black = {0, 0, SCREEN_WIDTH, SCREEN_HEIGHT}", "PICO - LOCKED"]
    for marker in forbidden:
        if marker in text:
            raise SystemExit(f"temporary Character Select fallback survived: {marker}")
    xtext = xml.read_text()
    if xtext.count('name = "csanim.bin"') != 1 or xtext.count('name = "cssfx.bin"') != 1 or xtext.count('name = "charsel.xa"') != 1:
        raise SystemExit("Character Select disc entries must appear exactly once")
    if "StageId_8_" in text or "SPAGHETTI" in text:
        raise SystemExit("later milestone content leaked into Character Select checkpoint")

    print("Applied full v0.8.4 Character Select PS1 runtime")


if __name__ == "__main__":
    main()
