#!/usr/bin/env python3
"""Replace instant Start-to-menu behavior with a base-Funkin pause menu."""
from __future__ import annotations

import argparse
from pathlib import Path


def once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


PAUSE_RUNTIME = r'''
typedef enum
{
	StagePauseMode_Standard = 0,
	StagePauseMode_Difficulty,
} StagePauseMode;

static FontData stage_pause_font;
static StagePauseMode stage_pause_mode = StagePauseMode_Standard;
static u8 stage_pause_select = 0;
static boolean stage_pause_just_opened = false;
static boolean stage_pause_practice = false;
static boolean stage_pause_keep_deaths = false;
static u16 stage_pause_deaths = 0;
static u32 stage_pause_animf = 0;
static fixed_t stage_pause_entry_x[6];
static fixed_t stage_pause_entry_y[6];
static char stage_pause_text[32];

static const char *Stage_PauseSongName(void)
{
	static const char *names[] = {
		"BOPEEBO", "FRESH", "DADBATTLE", "TUTORIAL",
		"SPOOKEEZ", "SOUTH", "MONSTER",
		"PICO", "PHILLY NICE", "BLAMMED",
		"SATIN PANTIES", "HIGH", "MILF", "TEST",
		"COCOA", "EGGNOG", "WINTER HORRORLAND",
		"SENPAI", "ROSES", "THORNS",
		"UGH", "GUNS", "STRESS",
		"WOCKY", "BEATHOVEN", "HAIRBALL", "NYAW",
		"IMPROBABLE OUTSET", "MADNESS", "HELLCLOWN", "EXPURGATION",
	};
	if (stage.stage_id < COUNT_OF(names))
		return names[stage.stage_id];
	return "UNKNOWN SONG";
}

static const char *Stage_PauseDifficultyName(StageDiff diff)
{
	switch (diff)
	{
		case StageDiff_Easy: return "EASY";
		case StageDiff_Normal: return "NORMAL";
		case StageDiff_Hard: return "HARD";
		case StageDiff_Erect: return "ERECT";
		case StageDiff_Nightmare: return "NIGHTMARE";
		default: return "UNKNOWN";
	}
}

static const char *Stage_PauseDeathText(void)
{
	char number[6];
	u16 value = stage_pause_deaths;
	u8 count = 0;
	do
	{
		number[count++] = '0' + (value % 10);
		value /= 10;
	}
	while (value != 0 && count < sizeof(number));

	char *dst = stage_pause_text;
	while (count != 0)
		*dst++ = number[--count];
	const char *suffix = " BLUE BALLS";
	while (*suffix != '\0' && dst < stage_pause_text + sizeof(stage_pause_text) - 1)
		*dst++ = *suffix++;
	*dst = '\0';
	return stage_pause_text;
}

static s32 Stage_PauseTextWidth(const char *text)
{
	s32 width = 0;
	while (*text != '\0')
	{
		char c = *text++;
		width += (c >= '0' && c <= '9') ? 8 : 13;
	}
	return width;
}

static void Stage_PauseDrawText(const char *text, s32 x, s32 y, FontAlign align, u8 colour)
{
	if (align == FontAlign_Center)
		x -= Stage_PauseTextWidth(text) >> 1;
	else if (align == FontAlign_Right)
		x -= Stage_PauseTextWidth(text);

	u32 variation = 0;
	u8 phase = (animf_count >> 1) & 1;
	u8 c;
	while ((c = *text++) != '\0')
	{
		if (c >= '0' && c <= '9')
		{
			RECT src = {80 + ((c - '0') << 3), 240, 8, 10};
			Gfx_BlitTexCol(&stage.tex_hud0, &src, x, y + 3, colour, colour, colour);
			x += 8;
			continue;
		}
		if ((c -= 'A') <= 'z' - 'A')
		{
			RECT src = {((c & 0x7) << 5) + ((((variation >> c) & 1) ^ phase) << 4), (c & ~0x7) << 1, 16, 16};
			Gfx_BlitTexCol(&stage_pause_font.tex, &src, x, y, colour, colour, colour);
			variation ^= 1 << c;
		}
		x += 13;
	}
}

static void Stage_PauseDrawPair(const char *prefix, const char *value, s32 right, s32 y, u8 colour)
{
	s32 value_width = Stage_PauseTextWidth(value);
	Stage_PauseDrawText(value, right, y, FontAlign_Right, colour);
	Stage_PauseDrawText(prefix, right - value_width, y, FontAlign_Right, colour);
}

static u8 Stage_PauseEntryCount(void)
{
	if (stage_pause_mode == StagePauseMode_Difficulty)
	{
		u8 count = 1; // Back
		for (u8 diff = StageDiff_Easy; diff < StageDiff_Max; diff++)
			if (Stage_SupportsDifficulty(stage.stage_id, (StageDiff)diff)) count++;
		return count;
	}
	return stage_pause_practice ? 4 : 5;
}

static StageDiff Stage_PauseDifficultyAt(u8 entry)
{
	for (u8 diff = StageDiff_Easy; diff < StageDiff_Max; diff++)
	{
		if (!Stage_SupportsDifficulty(stage.stage_id, (StageDiff)diff))
			continue;
		if (entry == 0)
			return (StageDiff)diff;
		entry--;
	}
	return StageDiff_Max;
}

static const char *Stage_PauseEntryName(u8 entry)
{
	if (stage_pause_mode == StagePauseMode_Difficulty)
	{
		StageDiff diff = Stage_PauseDifficultyAt(entry);
		return (diff == StageDiff_Max) ? "BACK" : Stage_PauseDifficultyName(diff);
	}
	static const char *standard[] = {
		"RESUME",
		"RESTART SONG",
		"CHANGE DIFFICULTY",
		"ENABLE PRACTICE MODE",
		"EXIT TO MENU",
	};
	if (stage_pause_practice && entry == 3)
		return standard[4];
	return standard[entry];
}

static void Stage_PauseResetLayout(boolean intro)
{
	for (u8 entry = 0; entry < 6; entry++)
	{
		if (intro)
		{
			stage_pause_entry_x[entry] = 0;
			stage_pause_entry_y[entry] = FIXED_DEC(10 + entry * 23,1);
		}
		else
		{
			s8 relative = (s8)entry - (s8)stage_pause_select;
			stage_pause_entry_x[entry] = FIXED_DEC(30 + relative * 9,1);
			stage_pause_entry_y[entry] = FIXED_DEC(115 + relative * 52,1);
		}
	}
}

static void Stage_PauseUpdateLayout(void)
{
	u8 count = Stage_PauseEntryCount();
	for (u8 entry = 0; entry < count; entry++)
	{
		s8 relative = (s8)entry - (s8)stage_pause_select;
		fixed_t target_x = FIXED_DEC(30 + relative * 9,1);
		fixed_t target_y = FIXED_DEC(115 + relative * 52,1);
		stage_pause_entry_x[entry] += (target_x - stage_pause_entry_x[entry]) >> 2;
		stage_pause_entry_y[entry] += (target_y - stage_pause_entry_y[entry]) >> 2;
	}
}

static void Stage_PauseDraw(void)
{
	Stage_PauseUpdateLayout();
	u8 metadata_colour = 0x80;

	// Submit text before the shade because the PS1 ordering table is LIFO.
	Stage_PauseDrawText(Stage_PauseSongName(), SCREEN_WIDTH - 10, 12, FontAlign_Right, metadata_colour);
	Stage_PauseDrawPair("ARTIST ", "KAWAI SPRITE", SCREEN_WIDTH - 10, 30, metadata_colour);
	Stage_PauseDrawPair("DIFFICULTY ", Stage_PauseDifficultyName(stage.stage_diff), SCREEN_WIDTH - 10, 48, metadata_colour);
	Stage_PauseDrawText(Stage_PauseDeathText(), SCREEN_WIDTH - 10, 66, FontAlign_Right, metadata_colour);
	if (stage_pause_practice)
		Stage_PauseDrawText("PRACTICE MODE", SCREEN_WIDTH - 10, 84, FontAlign_Right, metadata_colour);

	u8 count = Stage_PauseEntryCount();
	for (u8 entry = 0; entry < count; entry++)
	{
		s16 x = stage_pause_entry_x[entry] >> FIXED_SHIFT;
		s16 y = stage_pause_entry_y[entry] >> FIXED_SHIFT;
		if (y < 8 || y > SCREEN_HEIGHT - 18)
			continue;
		Stage_PauseDrawText(Stage_PauseEntryName(entry), x, y, FontAlign_Left,
			(entry == stage_pause_select) ? 0x80 : 0x4D);
	}

	RECT shade = {0, 0, SCREEN_WIDTH, SCREEN_HEIGHT};
	Gfx_DrawRectSemi(&shade, 0, 0, 0, 0);
}

static void Stage_PauseOpen(void)
{
	stage_pause_mode = StagePauseMode_Standard;
	stage_pause_select = 0;
	stage_pause_just_opened = true;
	stage_pause_animf = animf_count;
	Stage_PauseResetLayout(true);
	FontData_LoadPath(&stage_pause_font, "\\FONT\\PAUSEF.TIM;1");
	Audio_SaveXA();
	Audio_PlayXA_Offset("\\MUSIC\\PAUSE.XA;1", 0x30, 0, true, RandomRange(0, 30 * 75));
	stage.state = StageState_Pause;
	stage.pad_held = stage.pad_press = 0;
	Timer_Reset();
}

static void Stage_PauseResume(void)
{
	Audio_RestoreXA();
	stage.state = StageState_Play;
	stage.pad_held = stage.pad_press = 0;
	Timer_Reset();
}

static void Stage_PauseTransition(StageTrans target)
{
	Audio_DiscardSavedXA();
	Audio_StopXA();
	stage_pause_keep_deaths = (target == StageTrans_Reload);
	if (target == StageTrans_Menu)
	{
		stage_pause_practice = false;
		stage_pause_deaths = 0;
	}
	stage.trans = target;
	Trans_Start();
}

static void Stage_PauseTickInput(void)
{
	if (stage_pause_just_opened)
	{
		stage_pause_just_opened = false;
		return;
	}

	u8 count = Stage_PauseEntryCount();
	if (pad_state.press & PAD_UP)
		stage_pause_select = (stage_pause_select == 0) ? count - 1 : stage_pause_select - 1;
	if (pad_state.press & PAD_DOWN)
		stage_pause_select = (stage_pause_select + 1 >= count) ? 0 : stage_pause_select + 1;

	if (pad_state.press & PAD_CIRCLE)
	{
		if (stage_pause_mode == StagePauseMode_Difficulty)
		{
			stage_pause_mode = StagePauseMode_Standard;
			stage_pause_select = 0;
			Stage_PauseResetLayout(false);
		}
		else
		{
			Stage_PauseResume();
		}
		return;
	}

	if (!(pad_state.press & PAD_CROSS))
		return;

	if (stage_pause_mode == StagePauseMode_Difficulty)
	{
		StageDiff diff = Stage_PauseDifficultyAt(stage_pause_select);
		if (diff == StageDiff_Max)
		{
			stage_pause_mode = StagePauseMode_Standard;
			stage_pause_select = 0;
			Stage_PauseResetLayout(false);
		}
		else
		{
			stage.stage_diff = diff;
			Stage_PauseTransition(StageTrans_Reload);
		}
		return;
	}

	switch (stage_pause_select)
	{
		case 0:
			Stage_PauseResume();
			break;
		case 1:
			Stage_PauseTransition(StageTrans_Reload);
			break;
		case 2:
			stage_pause_mode = StagePauseMode_Difficulty;
			stage_pause_select = 0;
			Stage_PauseResetLayout(false);
			break;
		case 3:
			if (!stage_pause_practice)
			{
				stage_pause_practice = true;
				stage_pause_select = 0;
				Stage_PauseResetLayout(false);
			}
			else
			{
				Stage_PauseTransition(StageTrans_Menu);
			}
			break;
		default:
			Stage_PauseTransition(StageTrans_Menu);
			break;
	}
}

'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root
    gfx_h = root / "src/gfx.h"
    gfx_c = root / "src/gfx.c"
    audio_h = root / "src/audio.h"
    audio_c = root / "src/audio.c"
    stage_h = root / "src/stage.h"
    stage_c = root / "src/stage.c"
    font_h = root / "src/font.h"
    font_c = root / "src/font.c"
    xml = root / "funkin.xml"

    once(
        gfx_h,
        "void Gfx_DrawRect(const RECT *rect, u8 r, u8 g, u8 b);\n",
        "void Gfx_DrawRect(const RECT *rect, u8 r, u8 g, u8 b);\n"
        "void Gfx_DrawRectSemi(const RECT *rect, u8 r, u8 g, u8 b, u8 abr);\n",
        "semi-transparent rectangle declaration",
    )
    once(
        gfx_c,
        "void Gfx_BlitTexCol(Gfx_Tex *tex, const RECT *src, s32 x, s32 y, u8 r, u8 g, u8 b)\n{\n",
        r'''void Gfx_DrawRectSemi(const RECT *rect, u8 r, u8 g, u8 b, u8 abr)
{
	POLY_F4 *quad = (POLY_F4*)nextpri;
	setPolyF4(quad);
	setSemiTrans(quad, 1);
	setXYWH(quad, rect->x, rect->y, rect->w, rect->h);
	setRGB0(quad, r, g, b);
	addPrim(ot[db], quad);
	nextpri += sizeof(POLY_F4);

	DR_TPAGE *tpage = (DR_TPAGE*)nextpri;
	setDrawTPage(tpage, 0, 1, getTPage(0, abr & 3, 0, 0));
	addPrim(ot[db], tpage);
	nextpri += sizeof(DR_TPAGE);
}

void Gfx_BlitTexCol(Gfx_Tex *tex, const RECT *src, s32 x, s32 y, u8 r, u8 g, u8 b)
{
''',
        "semi-transparent rectangle runtime",
    )

    once(
        audio_h,
        "void Audio_PlayXA(const char *path, u8 volume, u8 channel, boolean loop);\n",
        "void Audio_PlayXA(const char *path, u8 volume, u8 channel, boolean loop);\n"
        "void Audio_PlayXA_Offset(const char *path, u8 volume, u8 channel, boolean loop, u32 sector_offset);\n",
        "offset XA declaration",
    )
    once(
        audio_h,
        "void Audio_PauseXA();\n",
        "void Audio_PauseXA();\n"
        "void Audio_SaveXA();\n"
        "void Audio_RestoreXA();\n"
        "void Audio_DiscardSavedXA();\n",
        "saved XA declarations",
    )
    once(
        audio_c,
        "void Audio_PauseXA()\n{\n",
        r'''void Audio_PlayXA_Offset(const char *path, u8 volume, u8 channel, boolean loop, u32 sector_offset)
{
	CdlFILE file;
	IO_FindFile(&file, path);
	u32 sectors = file.size / IO_SECT_SIZE;
	if (sector_offset >= sectors)
		sector_offset = 0;
	u32 start = CdPosToInt(&file.pos);

	XA_Init();
	XA_SetVolume(0);
	xa_start = start;
	xa_pos = start + sector_offset;
	xa_end = start + sectors - 1;
	xa_state = XA_STATE_INIT | XA_STATE_PLAYING | XA_STATE_SEEKING;
	xa_resync = 0;
	if (loop)
		xa_state |= XA_STATE_LOOPS;

	CdIntToPos(xa_pos, &file.pos);
	IO_SeekFile(&file);
	XA_SetFilter(channel);
	XA_SetVolume(volume);
}

void Audio_PauseXA()
{
''',
        "offset XA runtime",
    )
    once(
        audio_c,
        "static u32 xa_pos, xa_start, xa_end;\n",
        "static u32 xa_pos, xa_start, xa_end;\n\n"
        "static struct\n"
        "{\n"
        "\tboolean valid;\n"
        "\tu8 state, volume, channel;\n"
        "\tu32 pos, start, end;\n"
        "} xa_saved;\n",
        "saved XA state",
    )
    once(
        audio_c,
        "\txa_state = 0;\n\t\n\t//Get file positions",
        "\txa_state = 0;\n\txa_saved.valid = false;\n\t\n\t//Get file positions",
        "saved XA initialization",
    )
    once(
        audio_c,
        "void Audio_StopXA()\n{\n",
        r'''void Audio_SaveXA()
{
	xa_saved.valid = (xa_state & XA_STATE_PLAYING) != 0;
	if (xa_saved.valid)
	{
		xa_saved.state = xa_state;
		xa_saved.volume = xa_volume;
		xa_saved.channel = xa_channel;
		xa_saved.pos = xa_pos;
		xa_saved.start = xa_start;
		xa_saved.end = xa_end;
	}
	XA_Pause();
}

void Audio_RestoreXA()
{
	Audio_StopXA();
	if (!xa_saved.valid)
		return;

	XA_Init();
	xa_start = xa_saved.start;
	xa_pos = xa_saved.pos;
	xa_end = xa_saved.end;
	xa_channel = xa_saved.channel;
	xa_volume = xa_saved.volume;
	xa_state = (xa_saved.state | XA_STATE_PLAYING) & ~XA_STATE_SEEKING;
	XA_SetFilter(xa_channel);
	XA_SetVolume(xa_volume);
	XA_Play(xa_pos);
	xa_saved.valid = false;
}

void Audio_DiscardSavedXA()
{
	xa_saved.valid = false;
}

void Audio_StopXA()
{
''',
        "saved XA runtime",
    )

    once(
        font_h,
        "void FontData_Load(FontData *this, Font font);\n",
        "void FontData_Load(FontData *this, Font font);\n"
        "void FontData_LoadPath(FontData *this, const char *path);\n",
        "relocated font declaration",
    )
    once(
        font_c,
        "//Font functions\nvoid FontData_Load(FontData *this, Font font)\n",
        r'''//Font functions
void FontData_LoadPath(FontData *this, const char *path)
{
	Gfx_LoadTex(&this->tex, IO_Read(path), GFX_LOADTEX_FREE);
	this->get_width = Font_Bold_GetWidth;
	this->draw = Font_Bold_Draw;
}

void FontData_Load(FontData *this, Font font)
''',
        "relocated font loader",
    )

    once(
        stage_h,
        "\t\tStageState_Play, //Game is playing as normal\n",
        "\t\tStageState_Play, //Game is playing as normal\n"
        "\t\tStageState_Pause, //Base Funkin pause substate\n",
        "pause stage state",
    )
    once(
        stage_c,
        '#include "loadscr.h"\n',
        '#include "loadscr.h"\n#include "font.h"\n',
        "pause font include",
    )
    once(
        stage_c,
        "//Stage state\nStage stage;\n",
        "//Stage state\nStage stage;\n" + PAUSE_RUNTIME,
        "pause runtime helpers",
    )
    once(
        stage_c,
        r'''	//Tick transition
	if (pad_state.press & PAD_START)
	{
		//Return to menu
		stage.trans = (stage.state == StageState_Play) ? StageTrans_Menu : StageTrans_Reload;
		Trans_Start();
	}
''',
        r'''	//Start opens the real pause menu during play; death states keep retry behavior.
	if ((pad_state.press & PAD_START) && Trans_Idle())
	{
		if (stage.state == StageState_Play)
			Stage_PauseOpen();
		else if (stage.state == StageState_Pause)
			Stage_PauseResume();
		else
		{
			stage_pause_keep_deaths = true;
			stage.trans = StageTrans_Reload;
			Trans_Start();
		}
	}
''',
        "Start pause routing",
    )
    once(
        stage_c,
        "void Stage_Load(StageId id, StageDiff difficulty, boolean story)\n{\n",
        "void Stage_Load(StageId id, StageDiff difficulty, boolean story)\n"
        "{\n"
        "\tif (stage_pause_keep_deaths)\n"
        "\t\tstage_pause_keep_deaths = false;\n"
        "\telse\n"
        "\t\tstage_pause_deaths = 0;\n",
        "pause death counter load policy",
    )
    once(
        stage_c,
        "void Stage_NextLoad()\n{\n",
        "void Stage_NextLoad()\n"
        "{\n"
        "\tstage_pause_deaths = 0;\n",
        "pause death counter next-song reset",
    )
    once(
        stage_c,
        "\t\t\t\t\tstage.arrow_hitan[i]--;\n",
        "\t\t\t\t\tif (stage.state != StageState_Pause)\n"
        "\t\t\t\t\t\tstage.arrow_hitan[i]--;\n",
        "freeze receptor animation while paused",
    )
    once(
        stage_c,
        "\t\t\t//Display score\n",
        "\t\t\tStageDrawOnly:\n"
        "\t\t\tif (stage.state == StageState_Pause)\n"
        "\t\t\t\tStage_PauseDraw();\n\n"
        "\t\t\t//Display score\n",
        "pause draw label",
    )
    once(
        stage_c,
        "\t\tcase StageState_Dead: //Start BREAK animation and reading extra data from CD\n",
        "\t\tcase StageState_Pause:\n"
        "\t\t{\n"
        "\t\t\tStage_PauseTickInput();\n"
        "\t\t\t// Render the exact same stage frame beneath the pause substate.\n"
        "\t\t\ttimer_dt = 0;\n"
        "\t\t\tanimf_count = stage_pause_animf;\n"
        "\t\t\tstage.flag &= ~STAGE_FLAG_JUST_STEP;\n"
        "\t\t\tgoto StageDrawOnly;\n"
        "\t\t}\n"
        "\t\tcase StageState_Dead: //Start BREAK animation and reading extra data from CD\n",
        "pause state render route",
    )
    once(
        stage_c,
        "\t\t\tif (stage.health <= 0)\n"
        "\t\t\t{\n"
        "\t\t\t\t//Player has died\n"
        "\t\t\t\tstage.health = 0;\n"
        "\t\t\t\tstage.state = StageState_Dead;\n"
        "\t\t\t}\n",
        "\t\t\tif (stage.health <= 0)\n"
        "\t\t\t{\n"
        "\t\t\t\tif (stage_pause_practice)\n"
        "\t\t\t\t\tstage.health = 1;\n"
        "\t\t\t\telse\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\t//Player has died\n"
        "\t\t\t\t\tstage_pause_deaths++;\n"
        "\t\t\t\t\tstage.health = 0;\n"
        "\t\t\t\t\tstage.state = StageState_Dead;\n"
        "\t\t\t\t}\n"
        "\t\t\t}\n",
        "practice health guard",
    )

    once(
        xml,
        '\t\t\t\t<file name = "boldfont.tim" type = "data" source = "iso/font/boldfont.tim"/>\n',
        '\t\t\t\t<file name = "boldfont.tim" type = "data" source = "iso/font/boldfont.tim"/>\n'
        '\t\t\t\t<file name = "pausef.tim" type = "data" source = "iso/font/pausef.tim"/>\n',
        "pause font disc entry",
    )
    once(
        xml,
        '\t\t\t\t<file name = "menu.xa" type = "xa" source = "iso/music/menu.xa"/>\n',
        '\t\t\t\t<file name = "menu.xa" type = "xa" source = "iso/music/menu.xa"/>\n'
        '\t\t\t\t<file name = "pause.xa" type = "xa" source = "iso/music/pause.xa"/>\n',
        "pause XA disc entry",
    )

    combined = "\n".join(path.read_text().lower() for path in (gfx_h, gfx_c, audio_h, audio_c, font_h, font_c, stage_h, stage_c, xml))
    required = (
        "gfx_drawrectsemi",
        "audio_savexa",
        "audio_restorexa",
        "audio_playxa_offset",
        "stagestate_pause",
        "stage_pausedraw",
        "restart song",
        "change difficulty",
        "enable practice mode",
        "exit to menu",
        "pause.xa;1",
        "pausef.tim;1",
        "fontdata_loadpath",
    )
    for marker in required:
        if marker not in combined:
            raise SystemExit(f"pause menu v1 missing {marker}")
    print("Applied base-Funkin pause menu v1 with resumable XA context")


if __name__ == "__main__":
    main()
