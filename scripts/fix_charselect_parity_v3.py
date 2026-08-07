#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 3:
    raise SystemExit('usage: fix_charselect_parity_v3.py <builder.py> <runtime.py>')

builder = Path(sys.argv[1])
runtime = Path(sys.argv[2])


def between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    a = text.find(start)
    if a < 0:
        raise SystemExit(f'{label}: start anchor missing')
    b = text.find(end, a)
    if b < 0:
        raise SystemExit(f'{label}: end anchor missing')
    return text[:a] + replacement + text[b:]


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected one anchor, found {n}')
    return text.replace(old, new, 1)

b = builder.read_text()

b = once(
    b,
    'CLUT_BYTES = 16 * 2\nPIXEL_BYTES = SCENE_W * SCENE_H // 2\nRECORD_BYTES = CLUT_BYTES + PIXEL_BYTES\nCHAR_PIXEL_BYTES = CHAR_W * CHAR_H // 2\nCHAR_RECORD_BYTES = CLUT_BYTES + CHAR_PIXEL_BYTES',
    'PALETTE_COLORS = 16\nPALETTE_BYTES = PALETTE_COLORS * 2\nTILE_COLS = 4\nTILE_ROWS = 4\nPALETTE_COUNT = TILE_COLS * TILE_ROWS\nCLUT_BYTES = PALETTE_COUNT * PALETTE_BYTES\nPIXEL_BYTES = SCENE_W * SCENE_H // 2\nRECORD_BYTES = CLUT_BYTES + PIXEL_BYTES\nCHAR_PIXEL_BYTES = CHAR_W * CHAR_H // 2\nCHAR_RECORD_BYTES = CLUT_BYTES + CHAR_PIXEL_BYTES',
    'palette constants',
)

insert_anchor = '\ndef frame_record(frame: Image.Image) -> bytes:\n'
tiled = r'''
def quantize_tiled(frame: Image.Image, width: int, height: int, *, dither: bool) -> tuple[list[int], list[list[tuple[int, int, int]]]]:
    frame = frame.convert("RGBA")
    if frame.size != (width, height):
        raise ValueError(f"tile quantizer expected {(width, height)}, got {frame.size}")
    tile_w = width // TILE_COLS
    tile_h = height // TILE_ROWS
    if tile_w * TILE_COLS != width or tile_h * TILE_ROWS != height:
        raise ValueError("frame dimensions must divide evenly into the CLUT tile grid")

    indices = [0] * (width * height)
    palettes: list[list[tuple[int, int, int]]] = []
    for ty in range(TILE_ROWS):
        for tx in range(TILE_COLS):
            box = (tx * tile_w, ty * tile_h, (tx + 1) * tile_w, (ty + 1) * tile_h)
            tile = frame.crop(box)
            alpha = tile.getchannel("A")
            rgb = Image.new("RGB", tile.size, (0, 0, 0))
            rgb.paste(tile.convert("RGB"), mask=alpha)
            q = rgb.quantize(
                colors=15,
                method=Image.Quantize.MEDIANCUT,
                dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE,
            )
            raw = q.getpalette()[:45]
            colors = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
            while len(colors) < 15:
                colors.append((0, 0, 0))
            palettes.append(colors[:15])
            qpix = list(q.getdata())
            apix = list(alpha.getdata())
            for ly in range(tile_h):
                for lx in range(tile_w):
                    src = ly * tile_w + lx
                    dst = (ty * tile_h + ly) * width + (tx * tile_w + lx)
                    indices[dst] = 0 if apix[src] < 128 else int(qpix[src]) + 1
    return indices, palettes


def tiled_cluts(palettes: list[list[tuple[int, int, int]]]) -> bytes:
    if len(palettes) != PALETTE_COUNT:
        raise RuntimeError(f"expected {PALETTE_COUNT} tile palettes, got {len(palettes)}")
    out = bytearray()
    for colors in palettes:
        clut = [0] + [base.psx_color(c) for c in colors]
        out.extend(b"".join(struct.pack("<H", c) for c in clut))
    return bytes(out)

'''
if insert_anchor not in b:
    raise SystemExit('tile quantizer insertion anchor missing')
b = b.replace(insert_anchor, tiled + insert_anchor, 1)

b = between(
    b,
    'def frame_record(frame: Image.Image) -> bytes:\n',
    '\ndef mat_mul(a: Matrix, b: Matrix) -> Matrix:\n',
    r'''def frame_record(frame: Image.Image) -> bytes:
    indices, palettes = quantize_tiled(frame, SCENE_W, SCENE_H, dither=True)
    pal = tiled_cluts(palettes)
    pixels = pack_4bpp(indices, SCENE_W, SCENE_H)
    result = pal + pixels
    if len(result) != RECORD_BYTES:
        raise RuntimeError(f"Character Select scene frame record {len(result)} != {RECORD_BYTES}")
    return result


def char_frame_record(frame: Image.Image) -> bytes:
    indices, palettes = quantize_tiled(frame, CHAR_W, CHAR_H, dither=False)
    pal = tiled_cluts(palettes)
    pixels = pack_4bpp(indices, CHAR_W, CHAR_H)
    result = pal + pixels
    if len(result) != CHAR_RECORD_BYTES:
        raise RuntimeError(f"Character Select character frame record {len(result)} != {CHAR_RECORD_BYTES}")
    return result

''',
    'record encoders',
)

old_env_tail = '''    paste_static(scene, root, "charLight.png", 800, 250)\n    paste_static(scene, root, "charLight.png", 180, 240)\n    paste_anim(scene, anims.get("charSelectSpeakers"), -10, 0, i, count)\n    paste_static(scene, root, "foregroundBlur.png", -125, 170)\n\n    for png_name, xml_name, x, y in (\n        ("dipshitBlur.png", "dipshitBlur.xml", 419, -65),\n        ("dipshitBacking.png", "dipshitBacking.xml", 423, -17),\n    ):\n        png = root / "images" / "charSelect" / png_name\n        xml = root / "images" / "charSelect" / xml_name\n        if png.is_file() and xml.is_file():\n            scene.alpha_composite(sparrow_frame(png, xml, i, count), (x, y))\n    paste_static(scene, root, "chooseDipshit.png", 426, -13)\n    return crop_scene(scene)'''
new_env_tail = '''    paste_static(scene, root, "charLight.png", 800, 250)\n    paste_static(scene, root, "charLight.png", 180, 240)\n    return crop_scene(scene)'''
b = once(b, old_env_tail, new_env_tail, 'environment/front split')

old_char_tail = '''    # Same central 4:3 crop as the environment, but much higher resolution.\n    return scene.crop((160, 0, 1120, 720)).resize((CHAR_W, CHAR_H), Image.Resampling.LANCZOS)'''
new_char_tail = '''    # Official foreground order: speakers and foreground/card pieces are above\n    # GF/player, not flattened underneath them in the environment bank.\n    paste_anim(scene, anims.get("charSelectSpeakers"), -10, 0, i, count)\n    paste_static(scene, root, "foregroundBlur.png", -125, 170)\n    for png_name, xml_name, x, y in (\n        ("dipshitBlur.png", "dipshitBlur.xml", 419, -65),\n        ("dipshitBacking.png", "dipshitBacking.xml", 423, -17),\n    ):\n        png = root / "images" / "charSelect" / png_name\n        xml = root / "images" / "charSelect" / xml_name\n        if png.is_file() and xml.is_file():\n            scene.alpha_composite(sparrow_frame(png, xml, i, count), (x, y))\n    paste_static(scene, root, "chooseDipshit.png", 426, -13)\n    return scene.crop((160, 0, 1120, 720)).resize((CHAR_W, CHAR_H), Image.Resampling.LANCZOS)'''
b = once(b, old_char_tail, new_char_tail, 'foreground overlay order')

old_xa = '''    subprocess.run([str(psxavenc), "-t", "xa", "-f", "37800", "-b", "4", "-c", "2", "-F", "1", "-C", "0", str(source), str(out)], check=True)\n    if out.stat().st_size == 0 or out.stat().st_size % 2336:\n        raise RuntimeError("CHARSEL.XA is not a valid raw XA sector stream")'''
new_xa = '''    subprocess.run([str(psxavenc), "-t", "xa", "-f", "37800", "-b", "4", "-c", "2", "-F", "1", "-C", "0", str(source), str(out)], check=True)\n    raw = out.read_bytes()\n    if not raw or len(raw) % 2336:\n        raise RuntimeError("CHARSEL.XA encoder output is not a valid 2336-byte XA sector stream")\n    zero = bytes(2336)\n    physical = bytearray()\n    for pos in range(0, len(raw), 2336):\n        physical.extend(raw[pos:pos + 2336])\n        physical.extend(zero)\n        physical.extend(zero)\n        physical.extend(zero)\n    out.write_bytes(physical)\n    if out.stat().st_size != len(raw) * 4:\n        raise RuntimeError("CHARSEL.XA physical interleave size mismatch")'''
b = once(b, old_xa, new_xa, 'stayFunky physical XA interleave')

b = b.replace('"quality": "separate 256x192 4bpp character overlay with dedicated per-frame palette and no dithering"',
              '"quality": "256x192 4bpp overlay with sixteen spatial CLUTs; BF/GF/foreground preserve independent regional palettes"')
builder.write_text(b)

r = runtime.read_text()
r = once(r, '#define MENU_CS_CLUT_BYTES 32', '#define MENU_CS_PALETTE_COUNT 16\n#define MENU_CS_PALETTE_BYTES 32\n#define MENU_CS_CLUT_BYTES (MENU_CS_PALETTE_COUNT * MENU_CS_PALETTE_BYTES)', 'runtime CLUT size')

old_env_upload = '''\tRECT clut_upload = {\n\t\tmenu.tex_back.tim_crect.x,\n\t\tmenu.tex_back.tim_crect.y,\n\t\t16,\n\t\t1,\n\t};'''
r = once(r, old_env_upload, '''\tRECT clut_upload = {0, 510, 256, 1};''', 'environment CLUT upload')
old_char_upload = '''\tRECT clut_upload = {\n\t\tmenu.tex_title.tim_crect.x,\n\t\tmenu.tex_title.tim_crect.y,\n\t\t16,\n\t\t1,\n\t};'''
r = once(r, old_char_upload, '''\tRECT clut_upload = {0, 511, 256, 1};''', 'character CLUT upload')

lock_start = 'static void Menu_CSDrawLock(u8 index, s32 x, s32 y)\n{'
lock_end = 'static void Menu_CSDrawGrid(void)\n{'
r = between(
    r, lock_start, lock_end,
    r'''static void Menu_CSDrawLock(u8 index, s32 x, s32 y)
{
	u8 state = 0;
	if (index == menu_cs_grid)
		state = (menu_cs_mode == MenuCS_Deny) ? 2 : 1;
	RECT src = {state * 64, 0, 64, 64};
	RECT dst = {x, y, 32, 32};
	Gfx_DrawTex(&menu.tex_story, &src, &dst);
}

''',
    'lock colour path',
)

helper_anchor = 'static void Menu_CSDrawForeground(void)\n{'
tile_helper = r'''static void Menu_CSDrawTiled(Gfx_Tex *tex, const RECT *dst, s32 frame_w, s32 frame_h, s32 clut_y)
{
	const s32 cols = 4;
	const s32 rows = 4;
	const s32 tile_w = frame_w / cols;
	const s32 tile_h = frame_h / rows;
	for (s32 row = 0; row < rows; row++)
	{
		for (s32 col = 0; col < cols; col++)
		{
			u8 palette = (u8)(row * cols + col);
			Gfx_Tex tile = *tex;
			tile.clut = getClut(palette * 16, clut_y);
			RECT src = {col * tile_w, row * tile_h, tile_w, tile_h};
			s32 x0 = dst->x + (dst->w * col) / cols;
			s32 x1 = dst->x + (dst->w * (col + 1)) / cols;
			s32 y0 = dst->y + (dst->h * row) / rows;
			s32 y1 = dst->y + (dst->h * (row + 1)) / rows;
			RECT td = {x0, y0, x1 - x0, y1 - y0};
			Gfx_DrawTex(&tile, &src, &td);
		}
	}
}

'''
if helper_anchor not in r:
    raise SystemExit('tiled draw helper anchor missing')
r = r.replace(helper_anchor, tile_helper + helper_anchor, 1)

old_draw = '''\t\t\t// High-resolution character overlay is intentionally separate from the\n\t\t\t// 160x120 environment so BF/GF/locked art keeps its real linework/colors.\n\t\t\tif (menu_cs_mode != MenuCS_Intro)\n\t\t\t{\n\t\t\t\tRECT char_src = {0, 0, MENU_CS_CHAR_W, MENU_CS_CHAR_H};\n\t\t\t\tGfx_DrawTex(&menu.tex_title, &char_src, &scene_dst);\n\t\t\t}\n\t\t\tGfx_DrawTex(&menu.tex_back, &scene_src, &scene_dst);'''
new_draw = '''\t\t\t// OT is LIFO: foreground UI was submitted first, then this overlay,\n\t\t\t// then the back environment. Rendered order is back -> BF/GF + official\n\t\t\t// speakers/foreground/card -> selector/locks/nametag.\n\t\t\tif (menu_cs_mode != MenuCS_Intro)\n\t\t\t\tMenu_CSDrawTiled(&menu.tex_title, &scene_dst, MENU_CS_CHAR_W, MENU_CS_CHAR_H, 511);\n\t\t\tMenu_CSDrawTiled(&menu.tex_back, &scene_dst, MENU_CS_FRAME_W, MENU_CS_FRAME_H, 510);'''
r = once(r, old_draw, new_draw, 'tiled scene draw')

runtime.write_text(r)
print('Installed Character Select parity v3: 16 spatial CLUTs/layer, official foreground order, authored lock colours, 1:4 stayFunky XA interleave')
