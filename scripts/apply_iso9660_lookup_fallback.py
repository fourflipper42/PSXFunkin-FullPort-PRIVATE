#!/usr/bin/env python3
"""Apply full-directory ISO9660 lookup plus M1/M3 runtime repairs.

The giant disc has ISO9660 directories (including the root directory) that span
multiple 2048-byte sectors. PsyQ CdSearchFile is kept as the fast path, but a
non-fatal IO_SearchFile fallback scans every directory sector when PsyQ misses.
The movie player is routed through that same resolver, fixing cutscenes that
previously bypassed the boot-file fix. The final menu transition also becomes
the single owner of restoring Gettin' Freaky after Character Select/Freeplay.
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
 *
 * This fallback reads ISO9660 metadata directly only after CdSearchFile misses.
 * It understands the subset emitted by mkpsxiso: the primary volume descriptor,
 * nested directories, and ordinary ISO9660 file records.
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
	// Normal asset reads own the CD and therefore stop XA before seeking.
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
    text = io_c.read_text()
    count = text.count(OLD)
    if count != 1:
        raise SystemExit(f"IO_FindFile baseline anchor changed: expected 1, found {count}")
    io_c.write_text(text.replace(OLD, NEW, 1))

    io_h = root / "src/io.h"
    text = io_h.read_text()
    text = replace_once(
        text,
        "void IO_FindFile(CdlFILE *file, const char *path);\n",
        "boolean IO_SearchFile(CdlFILE *file, const char *path);\n"
        "void IO_FindFile(CdlFILE *file, const char *path);\n",
        "public nonfatal ISO search declaration",
    )
    io_h.write_text(text)


def patch_movies(root: Path) -> None:
    movie = root / "src/movie.c"
    text = movie.read_text()
    if '#include "io.h"' not in text:
        text = replace_once(text, '#include "main.h"\n', '#include "main.h"\n#include "io.h"\n#include "audio.h"\n', "movie IO/audio includes")
    movie_play = r'''void Movie_Play(const char *path, unsigned long length)
{
	// Movie playback owns the CD. Stop any XA stream before either the fallback
	// directory scan or STR streaming starts.
	Audio_StopXA();

	// Resolve with the same multi-sector ISO9660 path used by normal assets.
	// The full disc root is larger than one ISO sector, so raw CdSearchFile is
	// not reliable for the late MOVIE directory on all PsyQ revisions.
	CdlFILE file;
	if (!IO_SearchFile(&file, path))
	{
		sprintf(error_msg, "[Movie_Play] Missing \"%s\"", path);
		ErrorLock();
		return;
	}

	// Story selection can itself be confirmed with Start. Do not let that same
	// held press immediately skip the movie we are about to begin.
	while (PadRead(1) & PADstart)
		VSync(0);

	STRFILE sfile;
	strcpy(sfile.FileName, path);
	sfile.Xres = 320;
	sfile.Yres = 240;
	sfile.NumFrames = length;
	PlayStr(320, 240, 0, 0, &sfile);

	// Leave the drive quiescent. The next XA owner will reinitialize its own
	// filter/mode instead of inheriting STR streaming state.
	CdControlB(CdlPause, NULL, NULL);
	DrawSync(0);
	SetDispMask(1);
}
'''
    text = replace_c_function(text, "void Movie_Play(", movie_play, "movie playback function")
    movie.write_text(text)

    strplay = root / "src/strplay.c"
    text = strplay.read_text()
    old = "if (CdSearchFile(&file, str->FileName) == 0) {"
    new = "if (!IO_SearchFile(&file, str->FileName)) {"
    text = replace_once(text, old, new, "STR internal file lookup")
    strplay.write_text(text)


def patch_frontend_music(root: Path) -> None:
    menu = root / "src/menu.c"
    text = menu.read_text()

    # Character Select used to restore music from its visual teardown. Freeplay
    # had a second, separate restore path. Those paths race page/visual swaps.
    # Remove both and restore exactly once when the page transition commits.
    cs_restore = "\t\tMenu_RestoreMenuMusic();\n"
    if text.count(cs_restore) == 1:
        text = text.replace(
            cs_restore,
            "\t\t/* M3: frontend music restore is owned by page transition commit. */\n",
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
            "\t\t/* M3: frontend music restore is owned by page transition commit. */\n",
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
        "\tif (Trans_Tick())\n"
        "\t{\n"
        "\t\tu8 previous_page = menu.page;\n"
        "\t\t//Change to set next page\n"
        "\t\tmenu.page_swap = true;\n"
        "\t\tmenu.page = menu.next_page;\n"
        "\t\tmenu.select = menu.next_select;\n"
        "\n"
        "\t\t/* M1_M3_FRONTEND_AUDIO_RESTORE\n"
        "\t\t * Freeplay previews and Character Select use their own XA streams.\n"
        "\t\t * Restore Gettin' Freaky only after returning to an ordinary\n"
        "\t\t * frontend page, never while a Stage/Freeplay/CharacterSelect\n"
        "\t\t * destination is taking ownership of the CD. */\n"
        "\t\tif ((previous_page == MenuPage_Freeplay || previous_page == MenuPage_CharacterSelect) &&\n"
        "\t\t    menu.page != MenuPage_Stage && menu.page != MenuPage_Freeplay &&\n"
        "\t\t    menu.page != MenuPage_CharacterSelect)\n"
        "\t\t{\n"
        "\t\t\tAudio_StopXA();\n"
        "\t\t\tAudio_PlayXA_Track(XA_GettinFreaky, 0x40, 0, true);\n"
        "\t\t\tAudio_WaitPlayXA();\n"
        "\t\t\tstage.song_step = 0;\n"
        "\t\t}\n"
        "\t}\n"
    )
    text = replace_once(text, transition, transition_new, "central frontend audio transition")
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
    if "M1_M3_FRONTEND_AUDIO_RESTORE" not in menu:
        raise SystemExit("central frontend music restore marker missing")
    print("Applied ISO9660, STR playback lookup, and frontend audio ownership repairs")


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
