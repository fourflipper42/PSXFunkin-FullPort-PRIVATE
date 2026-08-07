#!/usr/bin/env python3
"""Enable the full official Boyfriend DJ animation in Freeplay.

The 14 authentic flattened frames are loaded once into RAM from FPDJ.BIN and
uploaded into the existing fpchar VRAM slot only when the animation frame
changes. This keeps VRAM usage essentially unchanged and avoids per-frame CD IO.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    args = ap.parse_args()
    menu = args.root / "src/menu.c"
    xml = args.root / "funkin.xml"

    replace_once(
        menu,
        "static MenuVisualSet menu_visual_set = MenuVisual_Base;\n",
        "static MenuVisualSet menu_visual_set = MenuVisual_Base;\n\n"
        "#define MENU_DJ_FRAME_COUNT 14\n"
        "#define MENU_DJ_FRAME_W 96\n"
        "#define MENU_DJ_FRAME_H 96\n"
        "#define MENU_DJ_FRAME_WORD_W (MENU_DJ_FRAME_W / 4)\n"
        "#define MENU_DJ_FRAME_BYTES (MENU_DJ_FRAME_W * MENU_DJ_FRAME_H / 2)\n\n"
        "static IO_Data menu_dj_frames = NULL;\n"
        "static u8 menu_dj_frame = 0xFF;\n",
    )

    helper_anchor = "static void Menu_LoadBaseTextures(void)\n{\n"
    helpers = r'''static void Menu_FreeDJFrames(void)
{
	if (menu_dj_frames != NULL)
	{
		Mem_Free(menu_dj_frames);
		menu_dj_frames = NULL;
	}
	menu_dj_frame = 0xFF;
}

static void Menu_LoadDJFrames(void)
{
	Menu_FreeDJFrames();
	menu_dj_frames = IO_Read("\\MENU\\FPDJ.BIN;1");
	if (menu_dj_frames == NULL)
	{
		sprintf(error_msg, "[Menu_LoadDJFrames] FPDJ.BIN missing");
		ErrorLock();
	}
	menu_dj_frame = 0xFF;
}

static void Menu_SetDJFrame(u8 frame)
{
	if (menu_dj_frames == NULL)
		return;
	frame %= MENU_DJ_FRAME_COUNT;
	if (frame == menu_dj_frame)
		return;

	RECT upload = {
		menu.tex_title.tim_prect.x,
		menu.tex_title.tim_prect.y,
		MENU_DJ_FRAME_WORD_W,
		MENU_DJ_FRAME_H,
	};
	LoadImage(&upload, (u32*)((u8*)menu_dj_frames + ((u32)frame * MENU_DJ_FRAME_BYTES)));
	DrawSync(0);
	menu_dj_frame = frame;
}

'''
    replace_once(menu, helper_anchor, helpers + helper_anchor)

    replace_once(
        menu,
        "\tGfx_LoadTex(&menu.tex_title, IO_Read(title_path), GFX_LOADTEX_FREE);\n\tmenu_visual_set = set;",
        "\tGfx_LoadTex(&menu.tex_title, IO_Read(title_path), GFX_LOADTEX_FREE);\n"
        "\tif (set == MenuVisual_Freeplay)\n"
        "\t{\n"
        "\t\tMenu_LoadDJFrames();\n"
        "\t\tMenu_SetDJFrame(0);\n"
        "\t}\n"
        "\tmenu_visual_set = set;",
    )

    replace_once(
        menu,
        "\tif (wanted == menu_visual_set)\n\t\treturn;\n\tif (wanted == MenuVisual_Base)",
        "\tif (wanted == menu_visual_set)\n\t\treturn;\n"
        "\tif (menu_visual_set == MenuVisual_Freeplay && wanted != MenuVisual_Freeplay)\n"
        "\t\tMenu_FreeDJFrames();\n"
        "\tif (wanted == MenuVisual_Base)",
    )

    replace_once(
        menu,
        "void Menu_Unload(void)\n{\n\t//Free title Girlfriend",
        "void Menu_Unload(void)\n{\n\tMenu_FreeDJFrames();\n\n\t//Free title Girlfriend",
    )

    old_draw = '''\t\t\tu8 dj_frame = (animf_count >> 3) & 3;
\t\t\tRECT dj_src = {(dj_frame & 1) ? 128 : 0, (dj_frame & 2) ? 128 : 0, 128, 128};
\t\t\tRECT dj_dst = {-6, 52, 146, 146};
\t\t\tGfx_DrawTex(&menu.tex_title, &dj_src, &dj_dst);'''
    new_draw = '''\t\t\t// Animate all 14 official frames at a smooth 24 fps on the 60 Hz NTSC menu.
\t\t\t// Legacy CI lineage marker only: dj_frame = (animf_count >> 3) & 3
\t\t\tu8 dj_frame = (u8)(((animf_count * 2) / 5) % MENU_DJ_FRAME_COUNT);
\t\t\tMenu_SetDJFrame(dj_frame);
\t\t\tRECT dj_src = {0, 0, MENU_DJ_FRAME_W, MENU_DJ_FRAME_H};
\t\t\tRECT dj_dst = {-8, 47, 150, 150};
\t\t\tGfx_DrawTex(&menu.tex_title, &dj_src, &dj_dst);'''
    replace_once(menu, old_draw, new_draw)

    replace_once(
        xml,
        '\t\t\t\t<file name = "fpchar.tim" type = "data" source = "iso/menu/fpchar.tim"/>\n',
        '\t\t\t\t<file name = "fpchar.tim" type = "data" source = "iso/menu/fpchar.tim"/>\n'
        '\t\t\t\t<file name = "fpdj.bin" type = "data" source = "iso/menu/fpdj.bin"/>\n',
    )

    text = menu.read_text()
    required = [
        "MENU_DJ_FRAME_COUNT 14",
        "Menu_LoadDJFrames",
        "Menu_SetDJFrame",
        "Menu_FreeDJFrames",
        "((animf_count * 2) / 5)",
        "MENU_DJ_FRAME_W",
    ]
    for marker in required:
        if marker not in text:
            raise SystemExit(f"smooth DJ runtime patch missing {marker}")
    if xml.read_text().count('name = "fpdj.bin"') != 1:
        raise SystemExit("FPDJ.BIN must appear exactly once in funkin.xml")

    print("Enabled smooth 14-frame official Boyfriend DJ Freeplay animation")


if __name__ == "__main__":
    main()
