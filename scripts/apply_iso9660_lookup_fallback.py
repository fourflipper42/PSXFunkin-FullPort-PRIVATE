#!/usr/bin/env python3
"""Apply the full-disc ISO resolver plus M1/M3 runtime repairs.

This patch is intentionally idempotent: Pico integration applies it once and the
final production guard may invoke it again to validate the already-patched tree.
M1 routes STR lookup through the proven ISO9660 fallback and moves the large STR
decode workspace from the PS1 stack to the engine heap. M3 defers restoring
Gettin' Freaky until after the destination menu visual set has finished all CD
asset reads, because IO_Read intentionally stops XA before seeking.
"""
from __future__ import annotations

import argparse
from pathlib import Path


OLD = r'''void IO_FindFile(CdlFILE *file, const char *path)
{
	printf("[IO_FindFile] Searching for %s\n", path);
	
	//Stop XA playback
	Audio_StopXA();
	
	//Search for file
	if (!CdSearchFile(file, (char*)path))
	{
		sprintf(error_msg, "[IO_FindFile] %s not found", path);
		ErrorLock();
	}
}
'''

NEW = r'''/*
 * PsyQ's CdSearchFile is retained as the normal fast path, but the full port
 * contains ISO9660 directories spanning multiple 2048-byte sectors. Some
 * PsyQ revisions fail to find records beyond the first directory sector.
 */
static u32 io_iso_sector[IO_SECT_SIZE / sizeof(u32)];

static u32 IO_ISOReadLE32(const u8 *p)
{
	return ((u32)p[0]) |
	       ((u32)p[1] << 8) |
	       ((u32)p[2] << 16) |
	       ((u32)p[3] << 24);
}

static u8 IO_ISOUpper(u8 c)
{
	if (c >= 'a' && c <= 'z')
		return c - ('a' - 'A');
	return c;
}

static boolean IO_ISONameEquals(const u8 *iso_name, u8 iso_len,
	const char *wanted, u8 wanted_len)
{
	u8 i;
	if (iso_len != wanted_len)
		return false;
	for (i = 0; i < iso_len; i++)
	{
		if (IO_ISOUpper(iso_name[i]) != IO_ISOUpper((u8)wanted[i]))
			return false;
	}
	return true;
}

static boolean IO_ReadISOSector(u32 lba)
{
	CdlLOC loc;
	CdIntToPos(lba, &loc);
	if (!CdControl(CdlSetloc, (u8*)&loc, NULL))
		return false;
	if (!CdRead(1, io_iso_sector, CdlModeSpeed))
		return false;
	return CdReadSync(0, NULL) == 0;
}

static boolean IO_ISOFindInDirectory(u32 dir_lba, u32 dir_size,
	const char *wanted, u8 wanted_len, u32 *extent, u32 *size, u8 *flags)
{
	u32 sector_count = (dir_size + IO_SECT_SIZE - 1) / IO_SECT_SIZE;
	u32 sector;

	for (sector = 0; sector < sector_count; sector++)
	{
		const u8 *data;
		u32 offset = 0;
		u32 consumed = sector * IO_SECT_SIZE;
		u32 limit = dir_size - consumed;
		if (limit > IO_SECT_SIZE)
			limit = IO_SECT_SIZE;

		if (!IO_ReadISOSector(dir_lba + sector))
			return false;
		data = (const u8*)io_iso_sector;

		while (offset < limit)
		{
			const u8 *record = data + offset;
			u8 record_len = record[0];
			u8 name_len;

			if (record_len == 0)
				break;
			if (record_len < 34 || offset + record_len > limit)
				break;

			name_len = record[32];
			if ((u32)33 + name_len <= record_len &&
			    IO_ISONameEquals(record + 33, name_len, wanted, wanted_len))
			{
				*extent = IO_ISOReadLE32(record + 2);
				*size = IO_ISOReadLE32(record + 10);
				*flags = record[25];
				return true;
			}
			offset += record_len;
		}
	}
	return false;
}

static boolean IO_ISOSearchFile(CdlFILE *file, const char *path)
{
	const u8 *pvd;
	const u8 *root;
	const char *cursor = path;
	u32 dir_lba;
	u32 dir_size;

	if (!IO_ReadISOSector(16))
		return false;
	pvd = (const u8*)io_iso_sector;
	if (pvd[0] != 1 || memcmp(pvd + 1, "CD001", 5) != 0 || pvd[6] != 1)
		return false;

	root = pvd + 156;
	if (root[0] < 34)
		return false;
	dir_lba = IO_ISOReadLE32(root + 2);
	dir_size = IO_ISOReadLE32(root + 10);

	while (*cursor == '\\' || *cursor == '/')
		cursor++;
	if (*cursor == '\0')
		return false;

	for (;;)
	{
		const char *component = cursor;
		u32 extent;
		u32 size;
		u8 flags;
		u8 component_len = 0;
		boolean last;

		while (*cursor != '\0' && *cursor != '\\' && *cursor != '/')
		{
			if (component_len == 255)
				return false;
			component_len++;
			cursor++;
		}
		if (component_len == 0)
			return false;

		last = (*cursor == '\0');
		if (!IO_ISOFindInDirectory(dir_lba, dir_size, component,
			component_len, &extent, &size, &flags))
			return false;

		if (last)
		{
			u8 copy_len = component_len < 15 ? component_len : 15;
			if (flags & 0x02)
				return false;
			CdIntToPos(extent, &file->pos);
			file->size = size;
			memcpy(file->name, component, copy_len);
			file->name[copy_len] = '\0';
			return true;
		}

		if (!(flags & 0x02))
			return false;
		dir_lba = extent;
		dir_size = size;
		while (*cursor == '\\' || *cursor == '/')
			cursor++;
		if (*cursor == '\0')
			return false;
	}
}

boolean IO_SearchFile(CdlFILE *file, const char *path)
{
	printf("[IO_SearchFile] Searching for %s\n", path);
	if (CdSearchFile(file, (char*)path))
		return true;
	printf("[IO_SearchFile] CdSearchFile miss, using full ISO9660 scan\n");
	return IO_ISOSearchFile(file, path);
}

void IO_FindFile(CdlFILE *file, const char *path)
{
	Audio_StopXA();
	if (!IO_SearchFile(file, path))
	{
		sprintf(error_msg, "[IO_FindFile] %s not found", path);
		ErrorLock();
	}
}
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def replace_c_function(text: str, signature: str, replacement: str, label: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"{label}: signature missing")
    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"{label}: opening brace missing")
    depth = 0
    end = -1
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end < 0:
        raise SystemExit(f"{label}: closing brace missing")
    return text[:start] + replacement.rstrip() + text[end:]


def patch_io(root: Path) -> None:
    io_c = root / "src/io.c"
    io_h = root / "src/io.h"
    text = io_c.read_text()

    if "boolean IO_SearchFile(CdlFILE *file, const char *path)" not in text:
        count = text.count(OLD)
        if count != 1:
            raise SystemExit(f"IO_FindFile baseline anchor changed: expected 1, found {count}")
        io_c.write_text(text.replace(OLD, NEW, 1))

    text_h = io_h.read_text()
    if "boolean IO_SearchFile(CdlFILE *file, const char *path);" not in text_h:
        text_h = replace_once(
            text_h,
            "void IO_FindFile(CdlFILE *file, const char *path);\n",
            "boolean IO_SearchFile(CdlFILE *file, const char *path);\n"
            "void IO_FindFile(CdlFILE *file, const char *path);\n",
            "public nonfatal ISO search declaration",
        )
        io_h.write_text(text_h)


def patch_movies(root: Path) -> None:
    movie = root / "src/movie.c"
    text = movie.read_text()
    if '#include "io.h"' not in text:
        text = replace_once(
            text,
            '#include "main.h"\n',
            '#include "main.h"\n#include "io.h"\n#include "audio.h"\n',
            "movie IO/audio includes",
        )

    movie_play = r'''void Movie_Play(const char *path, unsigned long length)
{
	Audio_StopXA();

	CdlFILE file;
	if (!IO_SearchFile(&file, path))
	{
		sprintf(error_msg, "[Movie_Play] Missing \"%s\"", path);
		ErrorLock();
		return;
	}

	// Do not let the Start press that selected Story Mode instantly skip the FMV.
	while (PadRead(1) & PADstart)
		VSync(0);

	STRFILE sfile;
	strcpy(sfile.FileName, path);
	sfile.Xres = 320;
	sfile.Yres = 240;
	sfile.NumFrames = length;
	PlayStr(320, 240, 0, 0, &sfile);

	CdControlB(CdlPause, NULL, NULL);
	DrawSync(0);
	SetDispMask(1);
}
'''
    # Replacing by function boundaries is safe on first and repeated application.
    text = replace_c_function(text, "void Movie_Play(", movie_play, "movie playback function")
    movie.write_text(text)

    strplay = root / "src/strplay.c"
    text = strplay.read_text()
    if '#include "mem.h"' not in text:
        text = replace_once(text, '#include "psx.h"\n', '#include "psx.h"\n#include "mem.h"\n', "STR heap include")

    raw_lookup = "if (CdSearchFile(&file, str->FileName) == 0) {"
    shared_lookup = "if (!IO_SearchFile(&file, str->FileName)) {"
    if raw_lookup in text:
        text = replace_once(text, raw_lookup, shared_lookup, "STR internal file lookup")
    elif shared_lookup not in text:
        raise SystemExit("STR lookup is neither raw CdSearchFile nor shared IO_SearchFile")

    # Legacy strplay placed the ring buffer, two VLC buffers and two MDEC slice
    # buffers on the stack. At 320x240 this is roughly 388 KiB. Story Mode calls
    # the movie before stage allocation, so borrow one contiguous heap block and
    # release it before Stage_Load continues.
    if "M1_STR_HEAP_WORKSPACE_V2" not in text:
        locals_old = r'''	u_long	RingBuff[RING_SIZE*SECTOR_SIZE];	// Ring buffer
	u_long	VlcBuff[2][str->Xres/2*str->Yres];	// VLC buffers
	u_short	ImgBuff[2][16*PPW*str->Yres];		// Frame 'slice' buffers
'''
        locals_new = r'''	/* M1_STR_HEAP_WORKSPACE_V2 */
	size_t ring_words = (size_t)RING_SIZE * (size_t)SECTOR_SIZE;
	size_t vlc_words = ((size_t)str->Xres / 2) * (size_t)str->Yres;
	size_t img_words = (size_t)(16 * PPW) * (size_t)str->Yres;
	size_t ring_bytes = ring_words * sizeof(u_long);
	size_t vlc_bytes = vlc_words * 2 * sizeof(u_long);
	size_t img_bytes = img_words * 2 * sizeof(u_short);
	u8 *workspace = NULL;
	u_long *RingBuff = NULL;
	u_long *VlcBuff = NULL;
	u_short *ImgBuff = NULL;
'''
        text = replace_once(text, locals_old, locals_new, "STR automatic decode buffers")

        lookup_end = r'''		SetDispMask(1);
		return;
	}
	
	// Setup the buffer pointers
'''
        allocation = r'''		SetDispMask(1);
		return;
	}

	workspace = (u8*)Mem_Alloc(ring_bytes + vlc_bytes + img_bytes);
	if (workspace == NULL)
	{
		sprintf(error_msg, "[strDoPlayback] no RAM for %lu-byte movie workspace",
		(unsigned long)(ring_bytes + vlc_bytes + img_bytes));
		ErrorLock();
		SetDispMask(1);
		return;
	}
	RingBuff = (u_long*)workspace;
	VlcBuff = (u_long*)(workspace + ring_bytes);
	ImgBuff = (u_short*)(workspace + ring_bytes + vlc_bytes);
	
	// Setup the buffer pointers
'''
        text = replace_once(text, lookup_end, allocation, "STR heap allocation point")

        ptrs_old = r'''	strEnv.VlcBuff_ptr[0] = &VlcBuff[0][0];
	strEnv.VlcBuff_ptr[1] = &VlcBuff[1][0];
	strEnv.VlcID     = 0;
	strEnv.ImgBuff_ptr[0] = &ImgBuff[0][0];
	strEnv.ImgBuff_ptr[1] = &ImgBuff[1][0];
'''
        ptrs_new = r'''	strEnv.VlcBuff_ptr[0] = VlcBuff;
	strEnv.VlcBuff_ptr[1] = VlcBuff + vlc_words;
	strEnv.VlcID     = 0;
	strEnv.ImgBuff_ptr[0] = ImgBuff;
	strEnv.ImgBuff_ptr[1] = ImgBuff + img_words;
'''
        text = replace_once(text, ptrs_old, ptrs_new, "STR heap buffer pointers")

        cleanup_old = r'''	DecDCToutCallback(0);
	StUnSetRing();
	CdControlB(CdlPause, 0, 0);
	
}
'''
        cleanup_new = r'''	DecDCToutCallback(0);
	StUnSetRing();
	CdControlB(CdlPause, 0, 0);
	Mem_Free(workspace);
	
}
'''
        text = replace_once(text, cleanup_old, cleanup_new, "STR heap workspace cleanup")

    strplay.write_text(text)


def patch_frontend_music(root: Path) -> None:
    menu = root / "src/menu.c"
    text = menu.read_text()

    # The standalone t0.12 compile diagnostic predates the full-port visual-set
    # manager and Character Select page. M3 only applies to the production menu.
    if "Menu_SyncV084Textures" not in text or "MenuPage_CharacterSelect" not in text:
        return
    if "M3_POST_VISUAL_AUDIO_RESTORE_V2" in text:
        return

    cs_restore = "\t\tMenu_RestoreMenuMusic();\n"
    if text.count(cs_restore) == 1:
        text = text.replace(
            cs_restore,
            "\t\t/* M3: defer music until destination visual CD reads finish. */\n",
            1,
        )
    elif text.count(cs_restore) != 0:
        raise SystemExit(f"Character Select music restore count changed: {text.count(cs_restore)}")

    freeplay_restore = (
        "\t\tif (page != MenuPage_Stage && page != MenuPage_CharacterSelect)\n"
        "\t\t{\n"
        "\t\t\tAudio_PlayXA_Track(XA_GettinFreaky, 0x40, 0, true);\n"
        "\t\t\tAudio_WaitPlayXA();\n"
        "\t\t}\n"
    )
    if text.count(freeplay_restore) == 1:
        text = text.replace(
            freeplay_restore,
            "\t\t/* M3: defer music until destination visual CD reads finish. */\n",
            1,
        )
    elif text.count(freeplay_restore) != 0:
        raise SystemExit(f"Freeplay music restore count changed: {text.count(freeplay_restore)}")

    transition = (
        "\tif (Trans_Tick())\n"
        "\t{\n"
        "\t\t//Change to set next page\n"
        "\t\tmenu.page_swap = true;\n"
        "\t\tmenu.page = menu.next_page;\n"
        "\t\tmenu.select = menu.next_select;\n"
        "\t}\n"
    )
    transition_new = (
        "\tboolean restore_frontend_music = false;\n"
        "\tif (Trans_Tick())\n"
        "\t{\n"
        "\t\tu8 previous_page = menu.page;\n"
        "\t\t//Change to set next page\n"
        "\t\tmenu.page_swap = true;\n"
        "\t\tmenu.page = menu.next_page;\n"
        "\t\tmenu.select = menu.next_select;\n"
        "\n"
        "\t\tif ((previous_page == MenuPage_Freeplay || previous_page == MenuPage_CharacterSelect) &&\n"
        "\t\t    menu.page != MenuPage_Stage && menu.page != MenuPage_Freeplay &&\n"
        "\t\t    menu.page != MenuPage_CharacterSelect)\n"
        "\t\t\trestore_frontend_music = true;\n"
        "\t}\n"
    )
    text = replace_once(text, transition, transition_new, "frontend audio transition flag")

    visual_sync = (
        "\t//Swap authentic v0.8.4 visual sets only when entering/leaving those pages.\n"
        "\tif (menu.page_swap)\n"
        "\t\tMenu_SyncV084Textures((MenuPage)menu.page);\n\n"
    )
    post_visual = visual_sync + (
        "\t/* M3_POST_VISUAL_AUDIO_RESTORE_V2\n"
        "\t * Menu_SyncV084Textures performs IO_Read calls, and IO_Read stops XA.\n"
        "\t * Restore menu music only after those destination asset reads finish. */\n"
        "\tif (restore_frontend_music)\n"
        "\t{\n"
        "\t\tMenu_RestoreMenuMusic();\n"
        "\t\tstage.song_step = 0;\n"
        "\t}\n\n"
    )
    text = replace_once(text, visual_sync, post_visual, "post-visual frontend audio restore")
    menu.write_text(text)


def validate(root: Path) -> None:
    io_c = (root / "src/io.c").read_text()
    io_h = (root / "src/io.h").read_text()
    movie = (root / "src/movie.c").read_text()
    strplay = (root / "src/strplay.c").read_text()
    menu = (root / "src/menu.c").read_text()

    for marker in (
        "IO_ISOSearchFile",
        "IO_ISOFindInDirectory",
        "IO_ReadISOSector(16)",
        "boolean IO_SearchFile(CdlFILE *file, const char *path)",
        "CdIntToPos(extent, &file->pos)",
    ):
        if marker not in io_c:
            raise SystemExit(f"ISO9660 runtime marker missing: {marker}")
    if "boolean IO_SearchFile(CdlFILE *file, const char *path);" not in io_h:
        raise SystemExit("IO_SearchFile declaration missing")
    if "IO_SearchFile(&file, path)" not in movie:
        raise SystemExit("Movie_Play does not use full ISO search")
    if "IO_SearchFile(&file, str->FileName)" not in strplay:
        raise SystemExit("STR player does not use full ISO search")
    if "CdSearchFile(&file, str->FileName)" in strplay:
        raise SystemExit("raw CdSearchFile survived inside STR player")
    if "M1_STR_HEAP_WORKSPACE_V2" not in strplay:
        raise SystemExit("STR player still uses the large automatic stack workspace")
    if "Menu_SyncV084Textures" in menu:
        if "M3_POST_VISUAL_AUDIO_RESTORE_V2" not in menu:
            raise SystemExit("post-visual frontend music restore marker missing")
        if "Menu_RestoreMenuMusic();" not in menu:
            raise SystemExit("post-visual menu music restore call missing")
    print("Applied/validated ISO9660, heap-backed STR playback, and post-visual frontend audio repairs")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    root = args.upstream
    patch_io(root)
    patch_movies(root)
    patch_frontend_music(root)
    validate(root)


if __name__ == "__main__":
    main()
