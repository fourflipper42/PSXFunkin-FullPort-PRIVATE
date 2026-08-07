#!/usr/bin/env python3
"""Final draw-order and navigation guards for the v0.8.4 menu foundation.

PSXFunkin inserts primitives at the head of one ordering-table bucket, so visual
background rectangles must be submitted *after* their text/foreground content.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    args = ap.parse_args()
    menu_c = args.root / "src" / "menu.c"

    replace_once(
        menu_c,
        '''\t\t\t\tif (pad_state.press & PAD_DOWN)\n\t\t\t\t{\n\t\t\t\t\tif (menu.select < COUNT_OF(menu_options) - 1) menu.select++;\n\t\t\t\t\telse menu.select = 0;\n\t\t\t\t}\n\n\t\t\t\t// Character Select is a distinct v0.8.4 menu.''',
        '''\t\t\t\tif (pad_state.press & PAD_DOWN)\n\t\t\t\t{\n\t\t\t\t\tif (menu.select < COUNT_OF(menu_options) - 1) menu.select++;\n\t\t\t\t\telse menu.select = 0;\n\t\t\t\t}\n\n\t\t\t\t// Never leave the selector displaying an unavailable Erect/Nightmare\n\t\t\t\t// chart after moving to a song that only has the legacy difficulties.\n\t\t\t\tif (!Stage_SupportsDifficulty(menu_options[menu.select].stage, menu.page_param.stage.diff))\n\t\t\t\t\tmenu.page_param.stage.diff = StageDiff_Hard;\n\n\t\t\t\t// Character Select is a distinct v0.8.4 menu.''',
    )

    replace_once(
        menu_c,
        '''\t\t\t\tRECT capsule = {132 + ((i == menu.select) ? 0 : 8), y - 10, (i == menu.select) ? 178 : 166, 22};\n\t\t\t\tif (i == menu.select)\n\t\t\t\t\tMenu_DrawPanel(&capsule, 238, 205, 89);\n\t\t\t\telse\n\t\t\t\t\tMenu_DrawPanel(&capsule, 63, 48, 79);\n\t\t\t\tmenu.font_bold.draw(&menu.font_bold,\n\t\t\t\t\tMenu_LowerIf(menu_options[i].text, i != menu.select),\n\t\t\t\t\t140 + ((i == menu.select) ? 0 : 8), y - 7, FontAlign_Left);''',
        '''\t\t\t\tRECT capsule = {132 + ((i == menu.select) ? 0 : 8), y - 10, (i == menu.select) ? 178 : 166, 22};\n\t\t\t\t// Text is submitted before its backing rectangle because addPrim()\n\t\t\t\t// prepends to the OT bucket; the later rectangle therefore draws behind it.\n\t\t\t\tmenu.font_bold.draw(&menu.font_bold,\n\t\t\t\t\tMenu_LowerIf(menu_options[i].text, i != menu.select),\n\t\t\t\t\t140 + ((i == menu.select) ? 0 : 8), y - 7, FontAlign_Left);\n\t\t\t\tif (i == menu.select)\n\t\t\t\t\tMenu_DrawPanel(&capsule, 238, 205, 89);\n\t\t\t\telse\n\t\t\t\t\tMenu_DrawPanel(&capsule, 63, 48, 79);''',
    )

    replace_once(menu_c, '"TRIANGLE CHARACTER"', '"TRI CHAR SELECT"')

    replace_once(
        menu_c,
        '''\t\t\t\tRECT card = {x - 56, 68, 112, 104};\n\t\t\t\tRECT face = {x - 38, 82, 76, 58};\n\t\t\t\tif (i == menu.select)\n\t\t\t\t\tMenu_DrawPanel(&card, 236, 188, 82);\n\t\t\t\telse\n\t\t\t\t\tMenu_DrawPanel(&card, 57, 52, 76);\n\t\t\t\tMenu_DrawPanel(&face, (i == MenuPlayer_Boyfriend) ? 48 : 74, (i == MenuPlayer_Boyfriend) ? 96 : 62, (i == MenuPlayer_Boyfriend) ? 147 : 77);\n\t\t\t\tmenu.font_bold.draw(&menu.font_bold, player_names[i], x, 148, FontAlign_Center);\n\t\t\t\tif (i == MenuPlayer_Pico)\n\t\t\t\t\tmenu.font_bold.draw(&menu.font_bold, "LOCKED", x, 162, FontAlign_Center);''',
        '''\t\t\t\tRECT card = {x - 56, 68, 112, 104};\n\t\t\t\tRECT face = {x - 38, 82, 76, 58};\n\t\t\t\tmenu.font_bold.draw(&menu.font_bold, player_names[i], x, 148, FontAlign_Center);\n\t\t\t\tif (i == MenuPlayer_Pico)\n\t\t\t\t\tmenu.font_bold.draw(&menu.font_bold, "LOCKED", x, 162, FontAlign_Center);\n\t\t\t\tMenu_DrawPanel(&face, (i == MenuPlayer_Boyfriend) ? 48 : 74, (i == MenuPlayer_Boyfriend) ? 96 : 62, (i == MenuPlayer_Boyfriend) ? 147 : 77);\n\t\t\t\tif (i == menu.select)\n\t\t\t\t\tMenu_DrawPanel(&card, 236, 188, 82);\n\t\t\t\telse\n\t\t\t\t\tMenu_DrawPanel(&card, 57, 52, 76);''',
    )

    text = menu_c.read_text()
    for needle in [
        "TRI CHAR SELECT",
        "StageDiff_Hard;",
        "Text is submitted before its backing rectangle",
        "PICO MIXES - NEXT CHECKPOINT",
    ]:
        if needle not in text:
            raise SystemExit(f"final menu source missing {needle!r}")

    print("Finalized v0.8.4 menu draw order and difficulty guards")


if __name__ == "__main__":
    main()
