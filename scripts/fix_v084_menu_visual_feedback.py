#!/usr/bin/env python3
"""Apply runtime corrections from the first v0.8.4 menu visual test.

Keeps the already-confirmed navigation/state behavior unchanged:
- official Boyfriend DJ animates in Freeplay;
- difficulty art is submitted before song names so it stays foreground;
- Character Select becomes a clean black official-icon selector.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one anchor, found {count}: {old[:120]!r}")
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
    menu = args.root / "src/menu.c"

    # The PSX OT is LIFO at this depth: submit difficulty before song names so
    # it is actually drawn after them and remains visually on top.
    replace_once(
        menu,
        "\t\t\t// Submit foreground first because the PS1 OT draws later submissions behind it.\n"
        "\t\t\tmenu.font_bold.draw(&menu.font_bold, \"FREEPLAY\", 10, 8, FontAlign_Left);",
        "\t\t\t// Difficulty must be the foremost raster over the song capsules/text.\n"
        "\t\t\tMenu_DrawV084Difficulty(244, 24);\n\n"
        "\t\t\t// Submit foreground first because the PS1 OT draws later submissions behind it.\n"
        "\t\t\tmenu.font_bold.draw(&menu.font_bold, \"FREEPLAY\", 10, 8, FontAlign_Left);",
    )
    replace_once(menu, "\n\t\t\tMenu_DrawV084Difficulty(244, 24);\n\n\t\t\t// Authentic BF chill art and Volume 1 album source art.", "\n\n\t\t\t// Official v0.8.4 Boyfriend DJ idle, flattened from the shipped Animate symbol.")

    old_bf = '''\t\t\tRECT bf_src = {0, 0, 128, 192};
\t\t\tRECT bf_dst = {-2, 38, 130, 192};
\t\t\tGfx_DrawTex(&menu.tex_title, &bf_src, &bf_dst);
\t\t\tRECT album_src = {144, 8, 96, 96};
\t\t\tRECT album_dst = {12, 20, 70, 70};
\t\t\tGfx_DrawTex(&menu.tex_title, &album_src, &album_dst);
\t\t\tRECT icon_src = {144, 120, 72, 64};
\t\t\tRECT icon_dst = {75, 20, 54, 48};
\t\t\tGfx_DrawTex(&menu.tex_title, &icon_src, &icon_dst);'''
    new_bf = '''\t\t\tu8 dj_frame = (animf_count >> 3) & 3;
\t\t\tRECT dj_src = {(dj_frame & 1) ? 128 : 0, (dj_frame & 2) ? 128 : 0, 128, 128};
\t\t\tRECT dj_dst = {-6, 52, 146, 146};
\t\t\tGfx_DrawTex(&menu.tex_title, &dj_src, &dj_dst);

\t\t\t// Volume 1 and BF icon remain authentic Freeplay assets on their own CLUT page.
\t\t\tRECT album_src = {0, 0, 64, 64};
\t\t\tRECT album_dst = {9, 18, 58, 58};
\t\t\tGfx_DrawTex(&menu.tex_ng, &album_src, &album_dst);
\t\t\tRECT icon_src = {64, 0, 64, 64};
\t\t\tRECT icon_dst = {72, 20, 48, 48};
\t\t\tGfx_DrawTex(&menu.tex_ng, &icon_src, &icon_dst);'''
    replace_once(menu, old_bf, new_bf)

    # Non-raw string is intentional: \t escape sequences below must become
    # actual tab characters in generated C rather than literal backslash-t.
    simple_character_select = '''\t\tcase MenuPage_CharacterSelect:
\t\t{
\t\t\tif (menu.page_swap)
\t\t\t{
\t\t\t\tmenu.select = menu_freeplay_player;
\t\t\t\tmenu.scroll = menu.select * FIXED_DEC(112,1);
\t\t\t}

\t\t\tif (menu.next_page == menu.page && Trans_Idle())
\t\t\t{
\t\t\t\tif (pad_state.press & PAD_LEFT)
\t\t\t\t{
\t\t\t\t\tif (menu.select > 0) menu.select--; else menu.select = MenuPlayer_Max - 1;
\t\t\t\t}
\t\t\t\tif (pad_state.press & PAD_RIGHT)
\t\t\t\t{
\t\t\t\t\tif (menu.select < MenuPlayer_Max - 1) menu.select++; else menu.select = 0;
\t\t\t\t}
\t\t\t\tif (pad_state.press & (PAD_START | PAD_CROSS))
\t\t\t\t{
\t\t\t\t\tif (menu.select == MenuPlayer_Boyfriend)
\t\t\t\t\t{
\t\t\t\t\t\tmenu_freeplay_player = MenuPlayer_Boyfriend;
\t\t\t\t\t\tmenu.next_page = MenuPage_Freeplay;
\t\t\t\t\t\tmenu.next_select = menu_freeplay_song;
\t\t\t\t\t\tTrans_Start();
\t\t\t\t\t}
\t\t\t\t}
\t\t\t\tif (pad_state.press & (PAD_CIRCLE | PAD_TRIANGLE))
\t\t\t\t{
\t\t\t\t\tmenu.next_page = MenuPage_Freeplay;
\t\t\t\t\tmenu.next_select = menu_freeplay_song;
\t\t\t\t\tTrans_Start();
\t\t\t\t}
\t\t\t}

\t\t\t// Deliberately simple PS1 presentation: black field + only official icons.
\t\t\t// Submit foreground first because this OT depth is LIFO.
\t\t\tmenu.font_bold.draw(&menu.font_bold, "CHARACTER SELECT", SCREEN_WIDTH2, 25, FontAlign_Center);
\t\t\tmenu.font_bold.draw(&menu.font_bold,
\t\t\t\t(menu.select == MenuPlayer_Boyfriend) ? "BOYFRIEND" : "PICO - LOCKED",
\t\t\t\tSCREEN_WIDTH2, 178, FontAlign_Center);
\t\t\tmenu.font_bold.draw(&menu.font_bold, "X SELECT   O BACK", SCREEN_WIDTH2, 211, FontAlign_Center);

\t\t\tif (menu.select == MenuPlayer_Pico)
\t\t\t{
\t\t\t\tRECT lock_src = {40, 98, 24, 24};
\t\t\t\tRECT lock_dst = {213, 108, 34, 34};
\t\t\t\tGfx_DrawTex(&menu.tex_ng, &lock_src, &lock_dst);
\t\t\t}

\t\t\tRECT bf_icon_src = {36, 0, 40, 36};
\t\t\tRECT bf_icon_dst = {51, 85, 88, 79};
\t\t\tGfx_DrawTex(&menu.tex_ng, &bf_icon_src, &bf_icon_dst);
\t\t\tRECT pico_icon_src = {78, 0, 48, 36};
\t\t\tRECT pico_icon_dst = {177, 87, 96, 72};
\t\t\tGfx_DrawTex(&menu.tex_ng, &pico_icon_src, &pico_icon_dst);

\t\t\tRECT selector_src = {0, 98, 32, 28};
\t\t\tRECT selector_dst = {(menu.select == MenuPlayer_Boyfriend) ? 39 : 169, 73, 112, 100};
\t\t\tGfx_DrawTex(&menu.tex_ng, &selector_src, &selector_dst);

\t\t\tRECT black = {0, 0, SCREEN_WIDTH, SCREEN_HEIGHT};
\t\t\tGfx_DrawRect(&black, 0, 0, 0);
\t\t\tbreak;
\t\t}
'''
    replace_between(menu, "\t\tcase MenuPage_CharacterSelect:", "\t\tcase MenuPage_Mods:", simple_character_select)

    text = menu.read_text()
    required = ["dj_frame = (animf_count >> 3) & 3", "PICO - LOCKED", "RECT black", "Menu_DrawV084Difficulty(244, 24)"]
    for marker in required:
        if marker not in text:
            raise SystemExit(f"feedback correction missing {marker}")
    if text.count("Menu_DrawV084Difficulty(244, 24)") != 1:
        raise SystemExit("difficulty should be submitted exactly once")
    if "Authentic BF chill art" in text:
        raise SystemExit("old Character Select BF art still used in Freeplay")
    if "\\t\\tcase MenuPage_CharacterSelect:" in text:
        raise SystemExit("literal \\t escapes leaked into generated menu.c")

    # Replace the compatibility four-sample loop with all 14 official frames.
    helper = Path(__file__).with_name("enable_freeplay_dj_stream.py")
    subprocess.run([sys.executable, str(helper), str(args.root)], check=True)


if __name__ == "__main__":
    main()
