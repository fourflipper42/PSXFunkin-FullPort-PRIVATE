#!/usr/bin/env python3
"""Switch the live Character Select renderer to native-resolution HQ assets.

Run after parity v3 and the v3 low-RAM patch. The existing low-resolution bank
is retained only for the one-time intro. Live Character Select uses a 320x240
16bpp background and 320x240 8bpp character/foreground frames.
"""
from pathlib import Path
import sys


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected one anchor, found {n}")
    return text.replace(old, new, 1)


def between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    a = text.find(start)
    if a < 0:
        raise SystemExit(f"{label}: start anchor missing")
    b = text.find(end, a + len(start))
    if b < 0:
        raise SystemExit(f"{label}: end anchor missing")
    return text[:a] + replacement + text[b:]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply_charselect_quality_v4.py <upstream>")
    root = Path(sys.argv[1])
    menu_path = root / "src" / "menu.c"
    xml_path = root / "funkin.xml"
    text = menu_path.read_text()

    # Keep the compact intro dimensions unchanged. Only the live character /
    # foreground stream becomes native 320x240 8bpp.
    replacements = [
        ("#define MENU_CS_CHAR_W 256", "#define MENU_CS_CHAR_W 320", "char width"),
        ("#define MENU_CS_CHAR_H 192", "#define MENU_CS_CHAR_H 240", "char height"),
        ("#define MENU_CS_CHAR_WORD_W (MENU_CS_CHAR_W / 4)", "#define MENU_CS_CHAR_WORD_W (MENU_CS_CHAR_W / 2)", "8bpp word width"),
        ("#define MENU_CS_CHAR_PIXEL_BYTES (MENU_CS_CHAR_W * MENU_CS_CHAR_H / 2)", "#define MENU_CS_CHAR_PIXEL_BYTES (MENU_CS_CHAR_W * MENU_CS_CHAR_H)", "8bpp pixel bytes"),
        ("#define MENU_CS_CHAR_IDLE_COUNT 12", "#define MENU_CS_CHAR_IDLE_COUNT 4", "idle count"),
        ("#define MENU_CS_CHAR_LOCKED_FIRST 12", "#define MENU_CS_CHAR_LOCKED_FIRST 4", "locked first"),
        ("#define MENU_CS_CHAR_LOCKED_COUNT 6", "#define MENU_CS_CHAR_LOCKED_COUNT 2", "locked count"),
        ("#define MENU_CS_CHAR_CONFIRM_FIRST 18", "#define MENU_CS_CHAR_CONFIRM_FIRST 6", "confirm first"),
        ("#define MENU_CS_CHAR_CONFIRM_COUNT 8", "#define MENU_CS_CHAR_CONFIRM_COUNT 3", "confirm count"),
        ("#define MENU_CS_CHAR_DENY_FIRST 26", "#define MENU_CS_CHAR_DENY_FIRST 9", "deny first"),
        ("#define MENU_CS_CHAR_DENY_COUNT 4", "#define MENU_CS_CHAR_DENY_COUNT 1", "deny count"),
        ("#define MENU_CS_CHAR_FRAME_COUNT 30", "#define MENU_CS_CHAR_FRAME_COUNT 10", "frame count"),
    ]
    for old, new, label in replacements:
        text = once(text, old, new, label)

    # The v3 RAM patch deliberately leaves a path-token comment for CI. Remove
    # the obsolete character-bank token now that live frames use CSCHAR8.RLE.
    stale_marker = "/* packed Character Select paths: CSANIM.RLE;1 CSCHAR.RLE;1 */"
    if text.count(stale_marker) != 1:
        raise SystemExit(f"stale v3 path marker: expected one anchor, found {text.count(stale_marker)}")
    text = text.replace(stale_marker, "/* compact Character Select intro path: CSANIM.RLE;1 */", 1)

    decoder_anchor = "static void Menu_FreeCSFrames(void)\n{"
    decoder = r'''#define MENU_CS_HQ_BG_VRAM_X 448
#define MENU_CS_HQ_CHAR_VRAM_X 768
#define MENU_CS_HQ_CLUT_X 448
#define MENU_CS_HQ_CLUT_Y 510
#define MENU_CS_HQ_W 320
#define MENU_CS_HQ_H 240

#define MENU_CS_Q2_MAGIC0 'C'
#define MENU_CS_Q2_MAGIC1 'S'
#define MENU_CS_Q2_MAGIC2 'Q'
#define MENU_CS_Q2_MAGIC3 '2'

static boolean Menu_CSQ2Decode(IO_Data bank, u8 frame, u8 expected_count, u32 expected_bytes, u8 *out)
{
	if (bank == NULL || out == NULL)
		return false;
	const u8 *base = (const u8*)bank;
	if (base[0] != MENU_CS_Q2_MAGIC0 || base[1] != MENU_CS_Q2_MAGIC1 ||
	    base[2] != MENU_CS_Q2_MAGIC2 || base[3] != MENU_CS_Q2_MAGIC3)
		return false;

	u16 count = (u16)base[4] | ((u16)base[5] << 8);
	u32 record_bytes = (u32)base[8] | ((u32)base[9] << 8) |
	                   ((u32)base[10] << 16) | ((u32)base[11] << 24);
	if (count != expected_count || record_bytes != expected_bytes || frame >= count)
		return false;

	const u8 *entry = base + 12 + ((u32)frame * 8);
	u32 offset = (u32)entry[0] | ((u32)entry[1] << 8) | ((u32)entry[2] << 16) | ((u32)entry[3] << 24);
	u32 packed = (u32)entry[4] | ((u32)entry[5] << 8) | ((u32)entry[6] << 16) | ((u32)entry[7] << 24);
	const u8 *src = base + offset;
	const u8 *end = src + packed;
	u32 written = 0;
	while (src < end && written < expected_bytes)
	{
		u8 control = *src++;
		if (control & 0x80)
		{
			u32 length = (u32)(control & 0x7F) + 3;
			if (src >= end || written + length > expected_bytes)
				return false;
			u8 value = *src++;
			while (length-- != 0)
				out[written++] = value;
		}
		else
		{
			u32 length = (u32)(control & 0x7F) + 1;
			if ((u32)(end - src) < length || written + length > expected_bytes)
				return false;
			while (length-- != 0)
				out[written++] = *src++;
		}
	}
	return written == expected_bytes;
}

static void Menu_UploadCSHQBackground(void)
{
	IO_Data pixels = IO_Read("\\MENU\\CSBG16.BIN;1");
	if (pixels == NULL)
	{
		sprintf(error_msg, "[Menu_UploadCSHQBackground] CSBG16.BIN missing");
		ErrorLock();
		return;
	}
	RECT image = {MENU_CS_HQ_BG_VRAM_X, 0, MENU_CS_HQ_W, MENU_CS_HQ_H};
	LoadImage(&image, (u32*)pixels);
	DrawSync(0);
	Mem_Free(pixels);
}

'''
    if decoder_anchor not in text:
        raise SystemExit("v4 decoder insertion anchor missing")
    text = text.replace(decoder_anchor, decoder + decoder_anchor, 1)

    load_start = "static void Menu_LoadCSFrames(void)\n{"
    load_end = "static void Menu_SetCSFrame(u8 frame)\n{"
    new_load = r'''static void Menu_LoadCSFrames(void)
{
	Menu_FreeCSFrames();
	// The compact bank is now intro-only. Live background is uploaded once at
	// full native resolution before XA playback begins.
	menu_cs_frames = IO_Read("\\MENU\\CSANIM.RLE;1");
	Menu_UploadCSHQBackground();
	menu_cs_char_frames = IO_Read("\\MENU\\CSCHAR8.RLE;1");
	if (menu_cs_frames == NULL || menu_cs_char_frames == NULL)
	{
		sprintf(error_msg, "[Menu_LoadCSFrames] Character Select HQ banks missing");
		ErrorLock();
	}
	menu_cs_uploaded_frame = 0xFF;
	menu_cs_uploaded_char_frame = 0xFF;
}

'''
    text = between(text, load_start, load_end, new_load, "HQ load path")

    char_start = "static void Menu_SetCSCharFrame(u8 frame)\n{"
    char_end = "static void Menu_LoadCSSfx(void)\n{"
    new_char = r'''static void Menu_SetCSCharFrame(u8 frame)
{
	if (menu_cs_char_frames == NULL)
		return;
	frame %= MENU_CS_CHAR_FRAME_COUNT;
	if (frame == menu_cs_uploaded_char_frame)
		return;

	u8 *record = (u8*)menu_cs_char_scratch;
	if (!Menu_CSQ2Decode(menu_cs_char_frames, frame, MENU_CS_CHAR_FRAME_COUNT, MENU_CS_CHAR_RECORD_BYTES, record))
	{
		sprintf(error_msg, "[Menu_SetCSCharFrame] corrupt HQ frame %d", frame);
		ErrorLock();
		return;
	}
	RECT clut_upload = {MENU_CS_HQ_CLUT_X, MENU_CS_HQ_CLUT_Y, 256, 1};
	RECT image_upload = {MENU_CS_HQ_CHAR_VRAM_X, 0, MENU_CS_CHAR_WORD_W, MENU_CS_CHAR_H};
	LoadImage(&clut_upload, (u32*)record);
	LoadImage(&image_upload, (u32*)(record + MENU_CS_CLUT_BYTES));
	DrawSync(0);
	menu_cs_uploaded_char_frame = frame;
}

'''
    text = between(text, char_start, char_end, new_char, "HQ char upload")

    draw_anchor = "static void Menu_CSDrawForeground(void)\n{"
    hq_draw = r'''static void Menu_CSDrawHQ8(const RECT *dst)
{
	// 320px 8bpp occupies 160 VRAM words = 128 + 128 + 64 texture pixels
	// across three 64-word texture pages.
	static const s16 widths[3] = {128, 128, 64};
	static const s16 offsets[3] = {0, 128, 256};
	for (u8 page = 0; page < 3; page++)
	{
		Gfx_Tex tex;
		tex.tim_mode = 1;
		tex.tpage = getTPage(1, 0, MENU_CS_HQ_CHAR_VRAM_X + page * 64, 0);
		tex.clut = getClut(MENU_CS_HQ_CLUT_X, MENU_CS_HQ_CLUT_Y);
		tex.pxshift = 1;
		RECT src = {0, 0, widths[page], MENU_CS_HQ_H};
		s32 x0 = dst->x + ((s32)dst->w * offsets[page]) / MENU_CS_HQ_W;
		s32 x1 = dst->x + ((s32)dst->w * (offsets[page] + widths[page])) / MENU_CS_HQ_W;
		RECT part = {x0, dst->y, x1 - x0, dst->h};
		Gfx_DrawTex(&tex, &src, &part);
	}
}

static void Menu_CSDrawHQ16(const RECT *dst)
{
	// Native 16bpp background spans five 64-word texture pages.
	for (u8 page = 0; page < 5; page++)
	{
		Gfx_Tex tex;
		tex.tim_mode = 2;
		tex.tpage = getTPage(2, 0, MENU_CS_HQ_BG_VRAM_X + page * 64, 0);
		tex.clut = 0;
		tex.pxshift = 0;
		RECT src = {0, 0, 64, MENU_CS_HQ_H};
		s32 x0 = dst->x + ((s32)dst->w * (page * 64)) / MENU_CS_HQ_W;
		s32 x1 = dst->x + ((s32)dst->w * ((page + 1) * 64)) / MENU_CS_HQ_W;
		RECT part = {x0, dst->y, x1 - x0, dst->h};
		Gfx_DrawTex(&tex, &src, &part);
	}
}

'''
    if draw_anchor not in text:
        raise SystemExit("HQ draw helper anchor missing")
    text = text.replace(draw_anchor, hq_draw + draw_anchor, 1)

    # The live background is static at full quality. Do not waste CPU/GPU time
    # uploading the obsolete 160x120 environment animation while XA is playing.
    live_env = "\t\t\t\tMenu_SetCSFrame(MENU_CS_ENV_FIRST + (u8)(((animf_count * 2) / 5) % MENU_CS_ENV_COUNT));\n"
    count = text.count(live_env)
    if count != 3:
        raise SystemExit(f"live environment update: expected 3 anchors, found {count}")
    text = text.replace(live_env, "", 3)

    # Two one-shot live environment uploads also become unnecessary.
    initial_env = "\t\t\t\t\tMenu_SetCSFrame(MENU_CS_ENV_FIRST);\n"
    count = text.count(initial_env)
    if count != 2:
        raise SystemExit(f"initial live env upload: expected 2 anchors, found {count}")
    text = text.replace(initial_env, "", 2)

    old_draw = '''\t\t\tRECT scene_src = {0, 0, MENU_CS_FRAME_W, MENU_CS_FRAME_H};\n\t\t\tRECT scene_dst;\n\t\t\tif (menu_cs_mode == MenuCS_Intro)\n\t\t\t\tscene_dst = (RECT){0, 0, SCREEN_WIDTH, SCREEN_HEIGHT};\n\t\t\telse\n\t\t\t\tscene_dst = (RECT){-6 - menu_cs_x * 3, -4 - menu_cs_y * 2, SCREEN_WIDTH + 12, SCREEN_HEIGHT + 8};\n\n\t\t\t// OT is LIFO: foreground UI was submitted first, then this overlay,\n\t\t\t// then the back environment. Rendered order is back -> BF/GF + official\n\t\t\t// speakers/foreground/card -> selector/locks/nametag.\n\t\t\tif (menu_cs_mode != MenuCS_Intro)\n\t\t\t\tMenu_CSDrawTiled(&menu.tex_title, &scene_dst, MENU_CS_CHAR_W, MENU_CS_CHAR_H, 511);\n\t\t\tMenu_CSDrawTiled(&menu.tex_back, &scene_dst, MENU_CS_FRAME_W, MENU_CS_FRAME_H, 510);'''
    new_draw = '''\t\t\tRECT scene_src = {0, 0, MENU_CS_FRAME_W, MENU_CS_FRAME_H};\n\t\t\tRECT scene_dst = {0, 0, SCREEN_WIDTH, SCREEN_HEIGHT};\n\n\t\t\tif (menu_cs_mode == MenuCS_Intro)\n\t\t\t{\n\t\t\t\t// Keep the already-working compact intro path only for the intro.\n\t\t\t\tMenu_CSDrawTiled(&menu.tex_back, &scene_dst, MENU_CS_FRAME_W, MENU_CS_FRAME_H, 510);\n\t\t\t}\n\t\t\telse\n\t\t\t{\n\t\t\t\t// OT is LIFO. Submission order here renders as:\n\t\t\t\t// 16bpp background -> 8bpp BF/GF + official foreground -> UI.\n\t\t\t\tMenu_CSDrawHQ8(&scene_dst);\n\t\t\t\tMenu_CSDrawHQ16(&scene_dst);\n\t\t\t}\n\t\t\t(void)scene_src;'''
    text = once(text, old_draw, new_draw, "HQ live draw path")

    text = once(text,
                "\t\t\t\tif (menu_cs_timer >= MENU_CS_CHAR_DENY_COUNT * 3)\n",
                "\t\t\t\tif (menu_cs_timer >= 12)\n",
                "deny hold time")

    menu_path.write_text(text)

    xml = xml_path.read_text()
    old_line = '\t\t\t\t<file name = "cschar.rle" type = "data" source = "iso/menu/cschar.rle"/>\n'
    if xml.count(old_line) != 1:
        raise SystemExit(f"old cschar.rle XML entry count {xml.count(old_line)}")
    xml = xml.replace(old_line,
                      '\t\t\t\t<file name = "csbg16.bin" type = "data" source = "iso/menu/csbg16.bin"/>\n'
                      '\t\t\t\t<file name = "cschar8.rle" type = "data" source = "iso/menu/cschar8.rle"/>\n', 1)
    xml_path.write_text(xml)

    low = text.lower()
    required = [
        "menu_cs_hq_bg_vram_x 448",
        "menu_cs_hq_char_vram_x 768",
        "menu_csq2decode",
        "csbg16.bin;1",
        "cschar8.rle;1",
        "menu_csdrawhq8",
        "menu_csdrawhq16",
        "#define menu_cs_char_w 320",
        "#define menu_cs_char_h 240",
        "#define menu_cs_char_frame_count 10",
    ]
    for marker in required:
        if marker not in low:
            raise SystemExit(f"quality v4 runtime missing {marker}")
    if 'io_read("\\\\menu\\\\cschar.rle;1")' in low:
        raise SystemExit("obsolete 4bpp live character bank still loaded")
    if "stageid_8_" in low or "spaghetti" in low:
        raise SystemExit("later milestone content leaked into quality v4")

    print("Applied Character Select quality v4: native 320x240 live renderer, 16bpp background, 8bpp character/foreground")


if __name__ == "__main__":
    main()
