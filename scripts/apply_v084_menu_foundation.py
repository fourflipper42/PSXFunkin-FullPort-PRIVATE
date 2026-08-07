#!/usr/bin/env python3
"""Apply the v0.8.4 Freeplay + Character Select menu foundation.

This is deliberately a menu-only checkpoint. It does not add Pico Mix charts,
Weekend 1 stages, or later content. Pico is shown as a locked future character
slot so the Character Select flow can be validated before playable Pico lands.
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
    ap.add_argument("root", type=Path, help="PSXFunkin source root after current difficulty patch")
    args = ap.parse_args()
    root = args.root

    menu_h = root / "src" / "menu.h"
    menu_c = root / "src" / "menu.c"

    replace_once(
        menu_h,
        "\tMenuPage_Freeplay,\n\tMenuPage_Mods,",
        "\tMenuPage_Freeplay,\n\tMenuPage_CharacterSelect,\n\tMenuPage_Mods,",
    )

    # Persistent menu-session state. This survives Menu_Load() calls so returning
    # from a song keeps the chosen Freeplay character/difficulty/song context.
    replace_once(
        menu_c,
        "//Menu state\nstatic struct\n{",
        "//v0.8.4 Freeplay / Character Select persistent state\n"
        "typedef enum\n"
        "{\n"
        "\tMenuPlayer_Boyfriend = 0,\n"
        "\tMenuPlayer_Pico,\n"
        "\tMenuPlayer_Max,\n"
        "} MenuPlayer;\n\n"
        "static MenuPlayer menu_freeplay_player = MenuPlayer_Boyfriend;\n"
        "static u8 menu_freeplay_song = 0;\n"
        "static StageDiff menu_freeplay_diff = StageDiff_Normal;\n\n"
        "//Menu state\nstatic struct\n{",
    )

    helper_anchor = "static const void Menu_DrawWeek(const char *week, s32 x, s32 y)"
    helpers = r'''static void Menu_DrawPanel(const RECT *rect, u8 r, u8 g, u8 b)
{
	Gfx_DrawRect(rect, r, g, b);
}

static void Menu_DrawModernFreeplayBack(void)
{
	// v0.8.4-inspired dark violet backing card and offset accent bands.
	RECT full = {0, 0, SCREEN_WIDTH, SCREEN_HEIGHT};
	RECT left = {0, 0, 126, SCREEN_HEIGHT};
	RECT top = {0, 0, SCREEN_WIDTH, 28};
	RECT bottom = {0, SCREEN_HEIGHT - 28, SCREEN_WIDTH, 28};
	RECT slash0 = {112, 28, 10, SCREEN_HEIGHT - 56};
	RECT slash1 = {122, 28, 4, SCREEN_HEIGHT - 56};
	Menu_DrawPanel(&full, 25, 17, 36);
	Menu_DrawPanel(&left, 43, 30, 62);
	Menu_DrawPanel(&top, 12, 10, 18);
	Menu_DrawPanel(&bottom, 12, 10, 18);
	Menu_DrawPanel(&slash0, 118, 72, 164);
	Menu_DrawPanel(&slash1, 236, 188, 82);
}

static void Menu_DrawCharacterSelectBack(void)
{
	// PS1-friendly reduction of the official stage/crowd character-select scene.
	RECT full = {0, 0, SCREEN_WIDTH, SCREEN_HEIGHT};
	RECT curtain_l = {0, 0, 34, SCREEN_HEIGHT};
	RECT curtain_r = {SCREEN_WIDTH - 34, 0, 34, SCREEN_HEIGHT};
	RECT stage_floor = {34, SCREEN_HEIGHT - 58, SCREEN_WIDTH - 68, 58};
	RECT light_l = {70, 38, 62, 130};
	RECT light_r = {SCREEN_WIDTH - 132, 38, 62, 130};
	Menu_DrawPanel(&full, 19, 22, 42);
	Menu_DrawPanel(&curtain_l, 92, 24, 62);
	Menu_DrawPanel(&curtain_r, 92, 24, 62);
	Menu_DrawPanel(&stage_floor, 43, 38, 57);
	Menu_DrawPanel(&light_l, 45, 74, 107);
	Menu_DrawPanel(&light_r, 45, 74, 107);
}

'''
    replace_once(menu_c, helper_anchor, helpers + helper_anchor)

    freeplay_case = r'''		case MenuPage_Freeplay:
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
				if (menu.select >= COUNT_OF(menu_options))
					menu.select = 0;
				menu.page_param.stage.diff = menu_freeplay_diff;
				if (!Stage_SupportsDifficulty(menu_options[menu.select].stage, menu.page_param.stage.diff))
					menu.page_param.stage.diff = StageDiff_Normal;
				menu.scroll = menu.select * FIXED_DEC(28,1);
			}

			if (menu.next_page == menu.page && Trans_Idle())
			{
				if (pad_state.press & PAD_UP)
				{
					if (menu.select > 0) menu.select--;
					else menu.select = COUNT_OF(menu_options) - 1;
				}
				if (pad_state.press & PAD_DOWN)
				{
					if (menu.select < COUNT_OF(menu_options) - 1) menu.select++;
					else menu.select = 0;
				}

				// Character Select is a distinct v0.8.4 menu. Triangle is the
				// controller-friendly equivalent of the official change-character hint.
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
					// Pico remains locked until the Pico Mix checkpoint. This keeps
					// the menu architecture real without routing BF songs to missing mixes.
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

			Menu_DifficultySelector(menu_options[menu.select].stage, true, SCREEN_WIDTH - 72, SCREEN_HEIGHT - 15);
			menu_freeplay_diff = menu.page_param.stage.diff;

			s32 next_scroll = menu.select * FIXED_DEC(28,1);
			menu.scroll += (next_scroll - menu.scroll) >> 3;

			// Render the v0.8.4 capsule-list concept using native PS1 primitives.
			for (u8 i = 0; i < COUNT_OF(menu_options); i++)
			{
				s32 y = 74 + (i * 28) - (menu.scroll >> FIXED_SHIFT);
				if (y < 34 || y > SCREEN_HEIGHT - 35) continue;
				RECT capsule = {132 + ((i == menu.select) ? 0 : 8), y - 10, (i == menu.select) ? 178 : 166, 22};
				if (i == menu.select)
					Menu_DrawPanel(&capsule, 238, 205, 89);
				else
					Menu_DrawPanel(&capsule, 63, 48, 79);
				menu.font_bold.draw(&menu.font_bold,
					Menu_LowerIf(menu_options[i].text, i != menu.select),
					140 + ((i == menu.select) ? 0 : 8), y - 7, FontAlign_Left);
			}

			// Left backing-card metadata / future DJ area.
			menu.font_bold.draw(&menu.font_bold, "FREEPLAY", 14, 10, FontAlign_Left);
			menu.font_bold.draw(&menu.font_bold,
				(menu_freeplay_player == MenuPlayer_Boyfriend) ? "BOYFRIEND" : "PICO",
				14, 48, FontAlign_Left);
			menu.font_bold.draw(&menu.font_bold, menu_options[menu.select].week, 14, 70, FontAlign_Left);
			menu.font_bold.draw(&menu.font_bold, "X PLAY", 14, SCREEN_HEIGHT - 49, FontAlign_Left);
			menu.font_bold.draw(&menu.font_bold, "TRIANGLE CHARACTER", 14, SCREEN_HEIGHT - 35, FontAlign_Left);
			menu.font_bold.draw(&menu.font_bold, "O BACK", 14, SCREEN_HEIGHT - 21, FontAlign_Left);

			Menu_DrawModernFreeplayBack();
			break;
		}
		case MenuPage_CharacterSelect:
		{
			static const char *player_names[] = {"BOYFRIEND", "PICO"};
			if (menu.page_swap)
			{
				menu.select = menu_freeplay_player;
				menu.scroll = menu.select * FIXED_DEC(112,1);
			}

			if (menu.next_page == menu.page && Trans_Idle())
			{
				if (pad_state.press & PAD_LEFT)
				{
					if (menu.select > 0) menu.select--;
					else menu.select = MenuPlayer_Max - 1;
				}
				if (pad_state.press & PAD_RIGHT)
				{
					if (menu.select < MenuPlayer_Max - 1) menu.select++;
					else menu.select = 0;
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
					// Pico intentionally rejects selection until his songs/runtime exist.
				}

				if (pad_state.press & (PAD_CIRCLE | PAD_TRIANGLE))
				{
					menu.next_page = MenuPage_Freeplay;
					menu.next_select = menu_freeplay_song;
					Trans_Start();
				}
			}

			menu.font_bold.draw(&menu.font_bold, "CHARACTER SELECT", SCREEN_WIDTH2, 13, FontAlign_Center);
			menu.font_bold.draw(&menu.font_bold, "CHOOSE YOUR PLAYER", SCREEN_WIDTH2, 31, FontAlign_Center);

			for (u8 i = 0; i < MenuPlayer_Max; i++)
			{
				s32 x = 70 + (i * 180);
				RECT card = {x - 56, 68, 112, 104};
				RECT face = {x - 38, 82, 76, 58};
				if (i == menu.select)
					Menu_DrawPanel(&card, 236, 188, 82);
				else
					Menu_DrawPanel(&card, 57, 52, 76);
				Menu_DrawPanel(&face, (i == MenuPlayer_Boyfriend) ? 48 : 74, (i == MenuPlayer_Boyfriend) ? 96 : 62, (i == MenuPlayer_Boyfriend) ? 147 : 77);
				menu.font_bold.draw(&menu.font_bold, player_names[i], x, 148, FontAlign_Center);
				if (i == MenuPlayer_Pico)
					menu.font_bold.draw(&menu.font_bold, "LOCKED", x, 162, FontAlign_Center);
			}

			if (menu.select == MenuPlayer_Boyfriend)
				menu.font_bold.draw(&menu.font_bold, "X SELECT  O BACK", SCREEN_WIDTH2, SCREEN_HEIGHT - 22, FontAlign_Center);
			else
				menu.font_bold.draw(&menu.font_bold, "PICO MIXES - NEXT CHECKPOINT", SCREEN_WIDTH2, SCREEN_HEIGHT - 22, FontAlign_Center);

			Menu_DrawCharacterSelectBack();
			break;
		}
'''

    replace_between(
        menu_c,
        "\t\tcase MenuPage_Freeplay:",
        "\t\tcase MenuPage_Mods:",
        freeplay_case,
    )

    checks = {
        menu_h: ["MenuPage_CharacterSelect"],
        menu_c: [
            "Menu_DrawModernFreeplayBack",
            "Menu_DrawCharacterSelectBack",
            "TRIANGLE CHARACTER",
            "PICO MIXES - NEXT CHECKPOINT",
            "menu_freeplay_diff",
        ],
    }
    for path, needles in checks.items():
        text = path.read_text()
        for needle in needles:
            if needle not in text:
                raise SystemExit(f"{path}: missing expected result {needle!r}")

    print("Applied v0.8.4 Freeplay/Character Select menu foundation")


if __name__ == "__main__":
    main()
