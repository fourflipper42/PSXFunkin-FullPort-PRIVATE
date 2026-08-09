#!/usr/bin/env python3
"""Apply console-native Options, Memory Card persistence, and Freeplay records."""

from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


SETTINGS_H = r'''#ifndef _SETTINGS_H
#define _SETTINGS_H

#include "psx.h"

#define SETTINGS_SCORE_SLOTS 64
#define SETTINGS_DIFF_SLOTS 5

typedef struct
{
	u8 master_volume;
	s8 screen_x;
	s8 screen_y;
	boolean expsync;
	boolean kade;
	boolean ghost;
	boolean downscroll;
	boolean reduced_flashing;
} GameSettings;

extern GameSettings settings;

void Settings_Init(void);
void Settings_Default(void);
void Settings_Apply(void);
boolean Settings_Save(void);
const char *Settings_StatusText(void);

u32 Settings_GetHighScore(u8 song, u8 difficulty);
u8 Settings_GetCompletion(u8 song, u8 difficulty);
void Settings_RecordResult(u8 song, u8 difficulty, s32 score);
u32 Settings_GetFavorites(u8 word);
void Settings_SetFavorites(u32 low, u32 high);

#endif
'''


SETTINGS_C = r'''#include "settings.h"

#include <libmcrd.h>

#include "audio.h"
#include "gfx.h"
#include "stage.h"
#include "settings_icon_generated.h"

#define SETTINGS_SAVE_PATH "bu00:BASCUS-PSXFUNKIN"
#define SETTINGS_SAVE_TITLE "PSXFUNKIN FULL PORT"
#define SETTINGS_MAGIC 0x31584650u
#define SETTINGS_VERSION 1

typedef enum
{
	SettingsStatus_Ready,
	SettingsStatus_Loaded,
	SettingsStatus_Saved,
	SettingsStatus_NoCard,
	SettingsStatus_Error,
	SettingsStatus_Defaults,
} SettingsStatus;

typedef struct
{
	u32 magic;
	u16 version;
	u16 size;
	u32 checksum;
	GameSettings options;
	u32 favorites[2];
	s32 high_scores[SETTINGS_SCORE_SLOTS][SETTINGS_DIFF_SLOTS];
	u8 completion[SETTINGS_SCORE_SLOTS][SETTINGS_DIFF_SLOTS];
} SettingsPayload;

typedef struct
{
	u16 id;
	u8 icon_display_flag;
	u8 icon_block_count;
	u8 title[64];
	u8 reserved[28];
	u8 icon_palette[32];
	u8 icon_pixels[128];
	u8 data[7936];
} SettingsSaveFile;

GameSettings settings;
static SettingsPayload settings_payload;
static SettingsSaveFile settings_file;
static SettingsStatus settings_status = SettingsStatus_Ready;

static boolean Settings_CardPresent(void)
{
	return _card_status(0) != 0x11;
}

static u32 Settings_Checksum(SettingsPayload *payload)
{
	u32 saved = payload->checksum;
	payload->checksum = 0;
	u32 hash = 2166136261u;
	const u8 *bytes = (const u8*)payload;
	for (u32 i = 0; i < sizeof(SettingsPayload); i++)
	{
		hash ^= bytes[i];
		hash *= 16777619u;
	}
	payload->checksum = saved;
	return hash;
}

static void Settings_ToShiftJIS(u8 *dst, const char *src)
{
	u8 *end = dst + 64;
	while (*src != '\0' && dst + 1 < end)
	{
		u8 c = (u8)*src++;
		*dst++ = 0x82;
		if (c >= '0' && c <= '9')
			*dst++ = 0x4F + c - '0';
		else if (c >= 'A' && c <= 'Z')
			*dst++ = 0x60 + c - 'A';
		else
			*dst++ = 0x40;
	}
}

void Settings_Default(void)
{
	settings.master_volume = 8;
	settings.screen_x = 0;
	settings.screen_y = 0;
	settings.expsync = true;
	settings.kade = true;
	settings.ghost = true;
	settings.downscroll = false;
	settings.reduced_flashing = false;
	settings_status = SettingsStatus_Defaults;
	Settings_Apply();
}

void Settings_Apply(void)
{
	if (settings.master_volume > 8)
		settings.master_volume = 8;
	if (settings.screen_x < -8)
		settings.screen_x = -8;
	if (settings.screen_x > 8)
		settings.screen_x = 8;
	if (settings.screen_y < -8)
		settings.screen_y = -8;
	if (settings.screen_y > 8)
		settings.screen_y = 8;

	stage.expsync = settings.expsync;
	stage.kade = settings.kade;
	stage.ghost = settings.ghost;
	stage.downscroll = settings.downscroll;
	stage.reduced_flashing = settings.reduced_flashing;
	Audio_SetMasterVolume(settings.master_volume);
	Gfx_SetScreenOffset(settings.screen_x, settings.screen_y);
}

void Settings_Init(void)
{
	memset(&settings_payload, 0, sizeof(settings_payload));
	Settings_Default();

	if (!Settings_CardPresent())
	{
		settings_status = SettingsStatus_NoCard;
		return;
	}

	int fd = open(SETTINGS_SAVE_PATH, 0x0001);
	if (fd < 0)
	{
		settings_status = SettingsStatus_Ready;
		return;
	}
	int got = read(fd, &settings_file, sizeof(settings_file));
	close(fd);
	if (got != sizeof(settings_file))
	{
		settings_status = SettingsStatus_Error;
		return;
	}

	SettingsPayload loaded;
	memcpy(&loaded, settings_file.data, sizeof(loaded));
	if (loaded.magic != SETTINGS_MAGIC ||
		loaded.version != SETTINGS_VERSION ||
		loaded.size != sizeof(SettingsPayload) ||
		loaded.checksum != Settings_Checksum(&loaded))
	{
		settings_status = SettingsStatus_Error;
		return;
	}

	settings_payload = loaded;
	settings = settings_payload.options;
	Settings_Apply();
	settings_status = SettingsStatus_Loaded;
}

boolean Settings_Save(void)
{
	if (!Settings_CardPresent())
	{
		settings_status = SettingsStatus_NoCard;
		return false;
	}

	settings_payload.magic = SETTINGS_MAGIC;
	settings_payload.version = SETTINGS_VERSION;
	settings_payload.size = sizeof(SettingsPayload);
	settings_payload.options = settings;
	settings_payload.checksum = 0;
	settings_payload.checksum = Settings_Checksum(&settings_payload);

	memset(&settings_file, 0, sizeof(settings_file));
	settings_file.id = 0x4353;
	settings_file.icon_display_flag = 0x11;
	settings_file.icon_block_count = 1;
	Settings_ToShiftJIS(settings_file.title, SETTINGS_SAVE_TITLE);
	memcpy(settings_file.icon_palette, settings_icon_palette, sizeof(settings_icon_palette));
	memcpy(settings_file.icon_pixels, settings_icon_pixels, sizeof(settings_icon_pixels));
	memcpy(settings_file.data, &settings_payload, sizeof(settings_payload));

	int fd = open(SETTINGS_SAVE_PATH, 0x0002);
	if (fd < 0)
		fd = open(SETTINGS_SAVE_PATH, 0x0202 | (1 << 16));
	if (fd < 0)
	{
		settings_status = SettingsStatus_Error;
		return false;
	}
	int wrote = write(fd, &settings_file, sizeof(settings_file));
	close(fd);
	if (wrote != sizeof(settings_file))
	{
		settings_status = SettingsStatus_Error;
		return false;
	}
	settings_status = SettingsStatus_Saved;
	return true;
}

const char *Settings_StatusText(void)
{
	switch (settings_status)
	{
		case SettingsStatus_Loaded: return "LOADED";
		case SettingsStatus_Saved: return "SAVED";
		case SettingsStatus_NoCard: return "NO CARD";
		case SettingsStatus_Error: return "CARD ERROR";
		case SettingsStatus_Defaults: return "DEFAULTS";
		default: return "READY";
	}
}

u32 Settings_GetHighScore(u8 song, u8 difficulty)
{
	if (song >= SETTINGS_SCORE_SLOTS || difficulty >= SETTINGS_DIFF_SLOTS)
		return 0;
	s32 score = settings_payload.high_scores[song][difficulty];
	return score > 0 ? (u32)score : 0;
}

u8 Settings_GetCompletion(u8 song, u8 difficulty)
{
	if (song >= SETTINGS_SCORE_SLOTS || difficulty >= SETTINGS_DIFF_SLOTS)
		return 0;
	return settings_payload.completion[song][difficulty] ? 100 : 0;
}

void Settings_RecordResult(u8 song, u8 difficulty, s32 score)
{
	if (song >= SETTINGS_SCORE_SLOTS || difficulty >= SETTINGS_DIFF_SLOTS)
		return;
	if (score < 0)
		score = 0;
	if (score > settings_payload.high_scores[song][difficulty])
		settings_payload.high_scores[song][difficulty] = score;
	settings_payload.completion[song][difficulty] = 1;
}

u32 Settings_GetFavorites(u8 word)
{
	return settings_payload.favorites[word & 1];
}

void Settings_SetFavorites(u32 low, u32 high)
{
	settings_payload.favorites[0] = low;
	settings_payload.favorites[1] = high;
}
'''


OPTIONS_CASE = r'''		case MenuPage_Options:
		{
			typedef enum
			{
				OptType_Boolean,
				OptType_Volume,
				OptType_Signed,
				OptType_Input,
				OptType_Scroll,
				OptType_Save,
				OptType_Defaults,
			} MenuOptionType;
			static const struct
			{
				MenuOptionType type;
				const char *text;
				void *value;
			} menu_options[] = {
				{OptType_Volume, "MUSIC VOLUME", &settings.master_volume},
				{OptType_Boolean, "AUDIO SYNC", &settings.expsync},
				{OptType_Input, "INPUT STYLE", &settings.kade},
				{OptType_Boolean, "GHOST TAPPING", &settings.ghost},
				{OptType_Scroll, "NOTE SCROLL", &settings.downscroll},
				{OptType_Boolean, "REDUCED FLASHING", &settings.reduced_flashing},
				{OptType_Signed, "SCREEN X", &settings.screen_x},
				{OptType_Signed, "SCREEN Y", &settings.screen_y},
				{OptType_Save, "SAVE SETTINGS", NULL},
				{OptType_Defaults, "RESET DEFAULTS", NULL},
			};

			if (menu.page_swap)
			{
				if (menu.select >= COUNT_OF(menu_options))
					menu.select = 0;
				menu.scroll = COUNT_OF(menu_options) * FIXED_DEC(24 + SCREEN_HEIGHT2,1);
				Settings_Apply();
			}

			menu.font_bold.draw(&menu.font_bold, "OPTIONS", 16, SCREEN_HEIGHT - 32, FontAlign_Left);
			menu.font_bold.draw(&menu.font_bold, "X CHANGE   O BACK", 165, SCREEN_HEIGHT - 14, FontAlign_Left);

			if (menu.next_page == menu.page && Trans_Idle())
			{
				if (pad_state.press & PAD_UP)
					menu.select = (menu.select == 0) ? COUNT_OF(menu_options) - 1 : menu.select - 1;
				if (pad_state.press & PAD_DOWN)
					menu.select = (menu.select + 1) % COUNT_OF(menu_options);

				s8 direction = 0;
				if (pad_state.press & PAD_LEFT)
					direction = -1;
				if (pad_state.press & (PAD_RIGHT | PAD_CROSS))
					direction = 1;

				if (direction != 0)
				{
					switch (menu_options[menu.select].type)
					{
						case OptType_Boolean:
						case OptType_Input:
						case OptType_Scroll:
							*((boolean*)menu_options[menu.select].value) ^= 1;
							Settings_Apply();
							break;
						case OptType_Volume:
						{
							s16 value = *((u8*)menu_options[menu.select].value) + direction;
							if (value < 0) value = 0;
							if (value > 8) value = 8;
							*((u8*)menu_options[menu.select].value) = (u8)value;
							Settings_Apply();
							break;
						}
						case OptType_Signed:
						{
							s16 value = *((s8*)menu_options[menu.select].value) + direction;
							if (value < -8) value = -8;
							if (value > 8) value = 8;
							*((s8*)menu_options[menu.select].value) = (s8)value;
							Settings_Apply();
							break;
						}
						case OptType_Save:
							if (pad_state.press & PAD_CROSS)
								Settings_Save();
							break;
						case OptType_Defaults:
							if (pad_state.press & PAD_CROSS)
								Settings_Default();
							break;
					}
				}

				if (pad_state.press & PAD_CIRCLE)
				{
					Settings_Save();
					menu.next_page = MenuPage_Main;
					menu.next_select = 3;
					Trans_Start();
				}
			}

			s32 next_scroll = menu.select * FIXED_DEC(24,1);
			menu.scroll += (next_scroll - menu.scroll) >> 4;
			for (u8 i = 0; i < COUNT_OF(menu_options); i++)
			{
				s32 y = (i * 24) - 8 - (menu.scroll >> FIXED_SHIFT);
				if (y <= -SCREEN_HEIGHT2 - 8) continue;
				if (y >= SCREEN_HEIGHT2 + 8) break;
				char text[0x80];
				switch (menu_options[i].type)
				{
					case OptType_Boolean:
						sprintf(text, "%s %s", menu_options[i].text, *((boolean*)menu_options[i].value) ? "ON" : "OFF");
						break;
					case OptType_Volume:
						sprintf(text, "%s %d / 8", menu_options[i].text, *((u8*)menu_options[i].value));
						break;
					case OptType_Signed:
						sprintf(text, "%s %d", menu_options[i].text, *((s8*)menu_options[i].value));
						break;
					case OptType_Input:
						sprintf(text, "%s %s", menu_options[i].text, *((boolean*)menu_options[i].value) ? "MODERN" : "CLASSIC");
						break;
					case OptType_Scroll:
						sprintf(text, "%s %s", menu_options[i].text, *((boolean*)menu_options[i].value) ? "DOWN" : "UP");
						break;
					case OptType_Save:
						sprintf(text, "%s %s", menu_options[i].text, Settings_StatusText());
						break;
					default:
						strcpy(text, menu_options[i].text);
						break;
				}
				menu.font_bold.draw(&menu.font_bold, Menu_LowerIf(text, menu.select != i), 48 + (y >> 2), SCREEN_HEIGHT2 + y - 8, FontAlign_Left);
			}

			Menu_DrawBack(true, 8, 253 >> 1, 113 >> 1, 155 >> 1, 0, 0, 0);
			break;
		}
'''


def find_case(text: str, start_marker: str, end_marker: str) -> tuple[int, int]:
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit(f"missing {start_marker}")
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit(f"missing {end_marker}")
    return start, end


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root

    generated = root / "src/settings_icon_generated.h"
    if not generated.is_file():
        raise SystemExit("settings_icon_generated.h must be built first")
    (root / "src/settings.h").write_text(SETTINGS_H)
    (root / "src/settings.c").write_text(SETTINGS_C)

    main_path = root / "src/main.c"
    text = main_path.read_text()
    text = replace_once(text, '#include "pad.h"\n', '#include "pad.h"\n#include "settings.h"\n#include <libmcrd.h>\n', "main includes")
    text = replace_once(text, '\tPad_Init();\n\tGfx_Init();\n\t\n\tTimer_Init();', '\tGfx_Init();\n\tInitCARD(1);\n\tPad_Init();\n\tStartCARD();\n\t_bu_init();\n\tSettings_Init();\n\t\n\tTimer_Init();', "main init")
    main_path.write_text(text)

    make_path = root / "Makefile"
    text = make_path.read_text()
    text = replace_once(text, '       src/audio.c \\\n', '       src/audio.c \\\n       src/settings.c \\\n', "settings source")
    text = replace_once(text, '#LDFLAGS += -lcard', 'LDFLAGS += -lcard', "card library")
    text = replace_once(text, '#LDFLAGS += -lmcrd', 'LDFLAGS += -lmcrd', "mcrd library")
    make_path.write_text(text)

    stage_h = root / "src/stage.h"
    text = stage_h.read_text()
    text = replace_once(text, 'boolean kade, ghost, downscroll, expsync;', 'boolean kade, ghost, downscroll, expsync, reduced_flashing;', "stage settings")
    stage_h.write_text(text)

    audio_h = root / "src/audio.h"
    text = audio_h.read_text()
    text = replace_once(text, 'void Audio_Init();\n', 'void Audio_Init();\nvoid Audio_SetMasterVolume(u8 volume);\nu8 Audio_GetMasterVolume(void);\n', "audio API")
    audio_h.write_text(text)

    audio_c = root / "src/audio.c"
    text = audio_c.read_text()
    text = replace_once(text, 'static u8 xa_state, xa_resync, xa_volume, xa_channel;', 'static u8 xa_state, xa_resync, xa_volume, xa_channel;\nstatic u8 audio_master_volume = 8;', "audio state")
    old = '''static void XA_SetVolume(u8 x)\n{\n\t//Set CD mix volume\n\tCdlATV cd_vol;\n\txa_volume = cd_vol.val0 = cd_vol.val1 = cd_vol.val2 = cd_vol.val3 = x;\n\tCdMix(&cd_vol);\n}\n'''
    new = '''static void XA_SetVolume(u8 x)\n{\n\t// Preserve the requested XA volume so pause/resume and master volume changes are lossless.\n\tCdlATV cd_vol;\n\txa_volume = x;\n\tu8 scaled = (u8)(((u16)x * audio_master_volume) / 8);\n\tcd_vol.val0 = cd_vol.val1 = cd_vol.val2 = cd_vol.val3 = scaled;\n\tCdMix(&cd_vol);\n}\n\nvoid Audio_SetMasterVolume(u8 volume)\n{\n\tif (volume > 8) volume = 8;\n\taudio_master_volume = volume;\n\tif (xa_state & XA_STATE_INIT)\n\t\tXA_SetVolume(xa_volume);\n}\n\nu8 Audio_GetMasterVolume(void)\n{\n\treturn audio_master_volume;\n}\n'''
    text = replace_once(text, old, new, "master volume")
    audio_c.write_text(text)

    gfx_h = root / "src/gfx.h"
    text = gfx_h.read_text()
    text = replace_once(text, 'void Gfx_DisableClear(void);\n', 'void Gfx_DisableClear(void);\nvoid Gfx_SetScreenOffset(s8 x, s8 y);\n', "gfx API")
    gfx_h.write_text(text)

    gfx_c = root / "src/gfx.c"
    text = gfx_c.read_text()
    text = replace_once(text, 'static u8 db;\n', 'static u8 db;\nstatic s8 gfx_screen_x = 0;\nstatic s8 gfx_screen_y = 0;\n', "gfx state")
    marker = 'void Gfx_SetClear(u8 r, u8 g, u8 b)\n'
    text = replace_once(text, marker, 'void Gfx_SetScreenOffset(s8 x, s8 y)\n{\n\tgfx_screen_x = x;\n\tgfx_screen_y = y;\n}\n\n' + marker, "gfx offset setter")
    rect_xy = 'setXYWH(quad, rect->x, rect->y, rect->w, rect->h);'
    if text.count(rect_xy) != 2:
        raise SystemExit(f"rect offsets: expected two matches, found {text.count(rect_xy)}")
    text = text.replace(rect_xy, 'setXYWH(quad, rect->x + gfx_screen_x, rect->y + gfx_screen_y, rect->w, rect->h);')
    text = replace_once(text, 'setXY0(sprt, x, y);', 'setXY0(sprt, x + gfx_screen_x, y + gfx_screen_y);', "blit offset")
    text = replace_once(text, '\t//Add quad\n\tPOLY_FT4 *quad = (POLY_FT4*)nextpri;\n\tsetPolyFT4(quad);\n\tsetUVWH(quad, csrc.x, csrc.y, csrc.w, csrc.h);\n\tsetXYWH(quad, cdst.x, cdst.y, cdst.w, cdst.h);', '\t//Add quad\n\tcdst.x += gfx_screen_x;\n\tcdst.y += gfx_screen_y;\n\tPOLY_FT4 *quad = (POLY_FT4*)nextpri;\n\tsetPolyFT4(quad);\n\tsetUVWH(quad, csrc.x, csrc.y, csrc.w, csrc.h);\n\tsetXYWH(quad, cdst.x, cdst.y, cdst.w, cdst.h);', "textured rect offset")
    arb_xy = 'setXY4(quad, p0->x, p0->y, p1->x, p1->y, p2->x, p2->y, p3->x, p3->y);'
    if text.count(arb_xy) != 2:
        raise SystemExit(f"arbitrary quad offsets: expected two matches, found {text.count(arb_xy)}")
    text = text.replace(arb_xy, 'setXY4(quad, p0->x + gfx_screen_x, p0->y + gfx_screen_y, p1->x + gfx_screen_x, p1->y + gfx_screen_y, p2->x + gfx_screen_x, p2->y + gfx_screen_y, p3->x + gfx_screen_x, p3->y + gfx_screen_y);')
    gfx_c.write_text(text)

    menu_path = root / "src/menu.c"
    text = menu_path.read_text()
    text = replace_once(text, '#include "audio.h"\n', '#include "audio.h"\n#include "settings.h"\n', "menu settings include")
    start, end = find_case(text, '\t\tcase MenuPage_Options:\n', '\t\tcase MenuPage_Stage:\n')
    text = text[:start] + OPTIONS_CASE + text[end:]
    text = replace_once(text, 'static u32 menu_fp_favorites = 0;', 'static u32 menu_fp_favorites[2] = {0, 0};', "64-slot favorites")
    text = replace_once(text, '\t\t\t\tmenu_fp_hold_direction = 0;\n\t\t\t\tmenu_fp_hold_frames = 0;', '\t\t\t\tmenu_fp_hold_direction = 0;\n\t\t\t\tmenu_fp_hold_frames = 0;\n\t\t\t\tmenu_fp_favorites[0] = Settings_GetFavorites(0);\n\t\t\t\tmenu_fp_favorites[1] = Settings_GetFavorites(1);', "load favorites")
    text = replace_once(
        text,
        '\t\t\t\tif ((pad_state.press & PAD_SQUARE) && menu.select != MENU_FP_RANDOM_OPTION)\n'
        '\t\t\t\t\tmenu_fp_favorites ^= (1u << Menu_FreeplaySongIndex(menu.select));',
        '\t\t\t\tif ((pad_state.press & PAD_SQUARE) && menu.select != MENU_FP_RANDOM_OPTION)\n'
        '\t\t\t\t{\n'
        '\t\t\t\t\tu8 favorite = Menu_FreeplaySongIndex(menu.select);\n'
        '\t\t\t\t\tmenu_fp_favorites[favorite >> 5] ^= (1u << (favorite & 31));\n'
        '\t\t\t\t\tSettings_SetFavorites(menu_fp_favorites[0], menu_fp_favorites[1]);\n'
        '\t\t\t\t\tSettings_Save();\n'
        '\t\t\t\t}',
        "toggle favorite",
    )
    text = replace_once(text, '(menu_fp_favorites & (1u << Menu_FreeplaySongIndex(menu.select)))', '(menu_fp_favorites[Menu_FreeplaySongIndex(menu.select) >> 5] & (1u << (Menu_FreeplaySongIndex(menu.select) & 31)))', "favorite display")
    text = replace_once(text, '\t\t\t\t\tmenu_freeplay_song = menu.select;\n\t\t\t\t\tmenu_freeplay_diff = menu.page_param.stage.diff;\n\t\t\t\t\tmenu.next_page = MenuPage_Main;', '\t\t\t\t\tmenu_freeplay_song = menu.select;\n\t\t\t\t\tmenu_freeplay_diff = menu.page_param.stage.diff;\n\t\t\t\t\tSettings_Save();\n\t\t\t\t\tmenu.next_page = MenuPage_Main;', "save freeplay exit")
    text = replace_once(text, 'static s16 Menu_FreeplayDrawNumber(u16 value, s16 x, s16 y, u8 width, u8 height)\n{\n\tu8 digits[5];', 'static s16 Menu_FreeplayDrawNumber(u32 value, s16 x, s16 y, u8 width, u8 height)\n{\n\tu8 digits[8];', "wide score digits")
    text = replace_once(text, 'Menu_FreeplayDrawNumber(0, 244, 40, 7, 11);', 'Menu_FreeplayDrawNumber(Settings_GetHighScore(song->stage, menu.page_param.stage.diff), 244, 40, 7, 11);', "personal best")
    text = replace_once(text, 'Menu_FreeplayDrawNumber(0, 224, 50, 7, 11);', 'Menu_FreeplayDrawNumber(Settings_GetCompletion(song->stage, menu.page_param.stage.diff), 224, 50, 7, 11);', "completion")
    text = replace_once(text, 'if (flash || (animf_count & 2) == 0)', 'if (flash || stage.reduced_flashing || (animf_count & 2) == 0)', "menu flashing reduction")
    white_flash = 'if (menu.trans_time >= 56)'
    if text.count(white_flash) != 2:
        raise SystemExit(f"white flash guards: expected two matches, found {text.count(white_flash)}")
    text = text.replace(white_flash, 'if (!stage.reduced_flashing && menu.trans_time >= 56)')
    menu_path.write_text(text)

    stage_c = root / "src/stage.c"
    text = stage_c.read_text()
    text = replace_once(text, '#include "audio.h"\n', '#include "audio.h"\n#include "settings.h"\n', "stage settings include")
    text = replace_once(text, 'static u32 stage_pause_animf = 0;', 'static u32 stage_pause_animf = 0;\nstatic boolean stage_result_recorded = false;', "result state")
    text = replace_once(text, '\tstage.score = 0;\n\tstrcpy(stage.score_text, "0");', '\tstage.score = 0;\n\tstrcpy(stage.score_text, "0");\n\tstage_result_recorded = false;', "result reset")
    text = replace_once(text, '\t\t\t\t//Song has ended\n\t\t\t\tplaying = false;', '\t\t\t\t//Song has ended\n\t\t\t\tplaying = false;\n\t\t\t\tif (!stage_result_recorded)\n\t\t\t\t{\n\t\t\t\t\tstage_result_recorded = true;\n\t\t\t\t\tif (!stage_pause_practice)\n\t\t\t\t\t{\n\t\t\t\t\t\tSettings_RecordResult(stage.stage_id, stage.stage_diff, stage.score * 10);\n\t\t\t\t\t\tSettings_Save();\n\t\t\t\t\t}\n\t\t\t\t}', "record result")
    stage_c.write_text(text)

    week2 = root / "src/stage/week2.c"
    text = week2.read_text()
    text = replace_once(text, 'if ((stage.flag & STAGE_FLAG_JUST_STEP) && (stage.song_step & 3) == 0)', 'if (!stage.reduced_flashing && (stage.flag & STAGE_FLAG_JUST_STEP) && (stage.song_step & 3) == 0)', "reduced lightning")
    week2.write_text(text)


if __name__ == "__main__":
    main()
