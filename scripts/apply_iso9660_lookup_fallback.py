#!/usr/bin/env python3
"""Apply the full-disc ISO resolver plus M1/M3 runtime repairs.

The ISO9660 fallback is the proven boot-file fix and remains unchanged in
principle. M1 v3 makes the legacy PsyQ STR player fail diagnostically instead
of feeding an uninitialized VLC buffer to MDEC when streaming never produces a
first frame. M3 v3 restores Gettin' Freaky only on a stable frontend frame,
after every page-swap teardown/load has completed.

The patch is intentionally idempotent because Pico integration invokes it and
the final production guard invokes it again.
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
        if text.count(OLD) != 1:
            raise SystemExit(f"IO_FindFile baseline anchor changed: expected 1, found {text.count(OLD)}")
        io_c.write_text(text.replace(OLD, NEW, 1))

    text = io_h.read_text()
    declaration = "boolean IO_SearchFile(CdlFILE *file, const char *path);\n"
    if declaration not in text:
        text = replace_once(
            text,
            "void IO_FindFile(CdlFILE *file, const char *path);\n",
            declaration + "void IO_FindFile(CdlFILE *file, const char *path);\n",
            "public nonfatal ISO search declaration",
        )
        io_h.write_text(text)


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
		sprintf(error_msg, "[M1V3 LOOKUP] missing %s", path);
		ErrorLock();
		return;
	}

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
    text = replace_c_function(text, "void Movie_Play(", movie_play, "movie playback function")
    movie.write_text(text)

    strplay = root / "src/strplay.c"
    text = strplay.read_text()
    if '#include "mem.h"' not in text:
        text = replace_once(text, '#include "psx.h"\n', '#include "psx.h"\n#include "mem.h"\n', "STR heap include")

    if "M1_STR_DIAGNOSTIC_V3" in text:
        strplay.write_text(text)
        return

    # Update prototypes before replacing the implementations.
    text = replace_once(
        text,
        "static void strNextVlc(STRENV *strEnv);\n",
        "static boolean strNextVlc(STRENV *strEnv);\n",
        "STR next VLC prototype",
    )
    text = replace_once(
        text,
        "static void strKickCD(CdlLOC *loc);\n",
        "static boolean strKickCD(CdlLOC *loc);\n",
        "STR CD kick prototype",
    )

    do_playback = r'''static void strDoPlayback(STRFILE *str) {
	/* M1_STR_DIAGNOSTIC_V3 */
	int id;
	DISPENV disp;
	CdlFILE file;

	/* Keep the large 320x240 decode workspace off the PS1 stack. */
	size_t ring_words = (size_t)RING_SIZE * (size_t)SECTOR_SIZE;
	size_t vlc_words = ((size_t)str->Xres / 2) * (size_t)str->Yres;
	size_t img_words = (size_t)(16 * PPW) * (size_t)str->Yres;
	size_t ring_bytes = ring_words * sizeof(u_long);
	size_t vlc_bytes = vlc_words * 2 * sizeof(u_long);
	size_t img_bytes = img_words * 2 * sizeof(u_short);
	u8 *workspace = NULL;
	u_long *RingBuff;
	u_long *VlcBuff;
	u_short *ImgBuff;

	SetDispMask(0);

	if (!IO_SearchFile(&file, str->FileName)) {
		SetDispMask(1);
		sprintf(error_msg, "[M1V3 E0] STR lookup failed");
		ErrorLock();
		return;
	}

	workspace = (u8*)Mem_Alloc(ring_bytes + vlc_bytes + img_bytes);
	if (workspace == NULL) {
		SetDispMask(1);
		sprintf(error_msg, "[M1V3 E1] no STR workspace RAM");
		ErrorLock();
		return;
	}
	RingBuff = (u_long*)workspace;
	VlcBuff = (u_long*)(workspace + ring_bytes);
	ImgBuff = (u_short*)(workspace + ring_bytes + vlc_bytes);

	strEnv.VlcBuff_ptr[0] = VlcBuff;
	strEnv.VlcBuff_ptr[1] = VlcBuff + vlc_words;
	strEnv.VlcID = 0;
	strEnv.ImgBuff_ptr[0] = ImgBuff;
	strEnv.ImgBuff_ptr[1] = ImgBuff + img_words;
	strEnv.ImgID = 0;

	strEnv.rect[0].x = strFrameX;
	strEnv.rect[0].y = strFrameY;
	strEnv.rect[1].x = strFrameX;
	strEnv.rect[1].y = strFrameY + strScreenHeight;
	strEnv.RectID = 0;
	strEnv.slice.x = strFrameX;
	strEnv.slice.y = strFrameY;
	strEnv.slice.w = 16 * PPW;
	strEnv.FrameDone = 0;

	DecDCTReset(0);
	DecDCToutCallback(strCallback);
	StSetRing(RingBuff, RING_SIZE);
	StSetStream(IS_RGB24, 1, 0xffffffff, 0, 0);

	if (!strKickCD(&file.pos)) {
		DecDCToutCallback(0);
		StUnSetRing();
		CdControlB(CdlPause, 0, 0);
		Mem_Free(workspace);
		SetDispMask(1);
		sprintf(error_msg, "[M1V3 E2] CD stream start failed");
		ErrorLock();
		return;
	}

	/* The legacy player ignored this failure and decoded uninitialized RAM. */
	if (!strNextVlc(&strEnv)) {
		DecDCToutCallback(0);
		StUnSetRing();
		CdControlB(CdlPause, 0, 0);
		Mem_Free(workspace);
		SetDispMask(1);
		sprintf(error_msg, "[M1V3 E3] no first STR frame");
		ErrorLock();
		return;
	}

	while (1) {
		DecDCTin(strEnv.VlcBuff_ptr[strEnv.VlcID], DCT_MODE);
		DecDCTout((u_long*)strEnv.ImgBuff_ptr[strEnv.ImgID], strEnv.slice.w * strEnv.slice.h / 2);

		if (!strNextVlc(&strEnv)) {
			DecDCToutCallback(0);
			StUnSetRing();
			CdControlB(CdlPause, 0, 0);
			Mem_Free(workspace);
			SetDispMask(1);
			sprintf(error_msg, "[M1V3 E4] STR frame stream stalled");
			ErrorLock();
			return;
		}

		strSync(&strEnv, 0);
		id = strEnv.RectID ? 0 : 1;
		SetDefDispEnv(&disp, 0, strScreenHeight * id, strScreenWidth * PPW, strScreenHeight);
#if IS_RGB24 == 1
		disp.isrgb24 = IS_RGB24;
		disp.disp.w = disp.disp.w * 2 / 3;
#endif
		VSync(0);
		PutDispEnv(&disp);
		SetDispMask(1);

		if (strPlayDone == 1)
			break;
		if (PadRead(1) & PADstart)
			break;
	}

	DecDCToutCallback(0);
	StUnSetRing();
	CdControlB(CdlPause, 0, 0);
	Mem_Free(workspace);
}
'''
    text = replace_c_function(
        text,
        "static void strDoPlayback(STRFILE *str) {",
        do_playback,
        "diagnostic STR playback",
    )

    next_vlc = r'''static boolean strNextVlc(STRENV *strEnv) {
	u_long *next = strNext(strEnv);
	if (next == 0)
		return false;

	strEnv->VlcID = strEnv->VlcID ? 0 : 1;
	DecDCTvlc(next, strEnv->VlcBuff_ptr[strEnv->VlcID]);
	StFreeRing(next);
	return true;
}
'''
    text = replace_c_function(
        text,
        "static void strNextVlc(STRENV *strEnv) {",
        next_vlc,
        "diagnostic next VLC",
    )

    next_frame = r'''static u_long *strNext(STRENV *strEnv) {
	u_long *addr;
	StHEADER *sector;
	u16 waits;

	/* Three seconds is far beyond a healthy first-frame latency at 2x speed. */
	for (waits = 0; waits < 180; waits++) {
		if (StGetNext((u_long **)&addr, (u_long **)&sector) == 0)
			break;
		VSync(0);
	}
	if (waits == 180)
		return 0;

	if (sector->frameCount >= strNumFrames)
		strPlayDone = 1;

	if (strFrameWidth != sector->width || strFrameHeight != sector->height) {
		RECT rect;
		setRECT(&rect, 0, 0, strScreenWidth * PPW, strScreenHeight * 2);
		ClearImage(&rect, 0, 0, 0);
		strFrameWidth = sector->width;
		strFrameHeight = sector->height;
	}

	strEnv->rect[0].w = strEnv->rect[1].w = strFrameWidth * PPW;
	strEnv->rect[0].h = strEnv->rect[1].h = strFrameHeight;
	strEnv->slice.h = strFrameHeight;
	return addr;
}
'''
    text = replace_c_function(
        text,
        "static u_long *strNext(STRENV *strEnv) {",
        next_frame,
        "bounded STR frame acquisition",
    )

    kick_cd = r'''static boolean strKickCD(CdlLOC *loc) {
	u_char param = CdlModeSpeed;
	u16 tries;

	for (tries = 0; tries < 120; tries++) {
		if (CdControl(CdlSetloc, (u_char *)loc, 0) != 0)
			break;
		VSync(0);
	}
	if (tries == 120)
		return false;

	for (tries = 0; tries < 120; tries++) {
		if (CdControl(CdlSetmode, &param, 0) != 0)
			break;
		VSync(0);
	}
	if (tries == 120)
		return false;

	VSync(3);
	for (tries = 0; tries < 30; tries++) {
		if (CdRead2(CdlModeStream | CdlModeSpeed | CdlModeRT) != 0)
			return true;
		VSync(0);
	}
	return false;
}
'''
    text = replace_c_function(
        text,
        "static void strKickCD(CdlLOC *loc) {",
        kick_cd,
        "bounded STR CD startup",
    )
    strplay.write_text(text)


def patch_frontend_music(root: Path) -> None:
    menu = root / "src/menu.c"
    text = menu.read_text()

    if "Menu_SyncV084Textures" not in text or "MenuPage_CharacterSelect" not in text:
        return
    if "M3_STABLE_FRAME_AUDIO_RESTORE_V3" in text:
        return

    # If an older v2 attempt is present, remove it before applying v3. Fresh
    # production trees normally enter through the baseline branch below.
    if "M3_POST_VISUAL_AUDIO_RESTORE_V2" in text:
        start = "\tboolean restore_frontend_music = false;\n\tif (Trans_Tick())\n"
        if start not in text:
            raise SystemExit("M3 v2 transition marker exists without expected block")
        # v2 is only expected on an already-patched diagnostic tree. Rebuild the
        # transition from function-local flag back to the baseline shape.
        old_transition = (
            "\tboolean restore_frontend_music = false;\n"
            "\tif (Trans_Tick())\n"
            "\t{\n"
            "\t\tu8 previous_page = menu.page;\n"
            "\t\t//Change to set next page\n"
            "\t\tmenu.page_swap = true;\n"
            "\t\tmenu.page = menu.next_page;\n"
            "\t\tmenu.select = menu.next_select;\n\n"
            "\t\tif ((previous_page == MenuPage_Freeplay || previous_page == MenuPage_CharacterSelect) &&\n"
            "\t\t    menu.page != MenuPage_Stage && menu.page != MenuPage_Freeplay &&\n"
            "\t\t    menu.page != MenuPage_CharacterSelect)\n"
            "\t\t\trestore_frontend_music = true;\n"
            "\t}\n"
        )
        baseline_transition = (
            "\tif (Trans_Tick())\n"
            "\t{\n"
            "\t\t//Change to set next page\n"
            "\t\tmenu.page_swap = true;\n"
            "\t\tmenu.page = menu.next_page;\n"
            "\t\tmenu.select = menu.next_select;\n"
            "\t}\n"
        )
        text = replace_once(text, old_transition, baseline_transition, "remove M3 v2 transition")
        visual = (
            "\t//Swap authentic v0.8.4 visual sets only when entering/leaving those pages.\n"
            "\tif (menu.page_swap)\n"
            "\t\tMenu_SyncV084Textures((MenuPage)menu.page);\n\n"
        )
        old_post = visual + (
            "\t/* M3_POST_VISUAL_AUDIO_RESTORE_V2\n"
            "\t * Menu_SyncV084Textures performs IO_Read calls, and IO_Read stops XA.\n"
            "\t * Restore menu music only after those destination asset reads finish. */\n"
            "\tif (restore_frontend_music)\n"
            "\t{\n"
            "\t\tMenu_RestoreMenuMusic();\n"
            "\t\tstage.song_step = 0;\n"
            "\t}\n\n"
        )
        text = replace_once(text, old_post, visual, "remove M3 v2 post-visual restore")

    # Remove page-specific restore calls. Character Select can perform a font
    # reload after its visual teardown, and that IO path would stop XA again.
    cs_restore = "\t\tMenu_RestoreMenuMusic();\n"
    if text.count(cs_restore) == 1:
        text = text.replace(cs_restore, "\t\t/* M3 v3: stable-frame owner restores frontend XA. */\n", 1)
    elif text.count(cs_restore) > 1:
        raise SystemExit(f"Character Select restore count changed: {text.count(cs_restore)}")

    freeplay_restore = (
        "\t\tif (page != MenuPage_Stage && page != MenuPage_CharacterSelect)\n"
        "\t\t{\n"
        "\t\t\tAudio_PlayXA_Track(XA_GettinFreaky, 0x40, 0, true);\n"
        "\t\t\tAudio_WaitPlayXA();\n"
        "\t\t}\n"
    )
    if text.count(freeplay_restore) == 1:
        text = text.replace(freeplay_restore, "\t\t/* M3 v3: stable-frame owner restores frontend XA. */\n", 1)
    elif text.count(freeplay_restore) > 1:
        raise SystemExit(f"Freeplay restore count changed: {text.count(freeplay_restore)}")

    state_anchor = "//Menu state\nstatic struct\n{"
    state_new = (
        "/* M3_STABLE_FRAME_AUDIO_RESTORE_V3 */\n"
        "static u8 menu_restore_frontend_music_pending = 0;\n\n"
        + state_anchor
    )
    text = replace_once(text, state_anchor, state_new, "M3 persistent pending state")

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
        "\t\tmenu.select = menu.next_select;\n\n"
        "\t\tif ((previous_page == MenuPage_Freeplay || previous_page == MenuPage_CharacterSelect) &&\n"
        "\t\t    menu.page != MenuPage_Stage && menu.page != MenuPage_Freeplay &&\n"
        "\t\t    menu.page != MenuPage_CharacterSelect)\n"
        "\t\t\tmenu_restore_frontend_music_pending = 2;\n"
        "\t}\n"
    )
    text = replace_once(text, transition, transition_new, "M3 transition pending flag")

    tail = "\t//Clear page swap flag\n\tmenu.page_swap = menu.page != exec_page;\n}"
    tail_new = r'''	//Clear page swap flag
	menu.page_swap = menu.page != exec_page;

	/* Wait through one completely stable frontend tick. This is deliberately
	 * later than Menu_SyncV084Textures, Character Select teardown/font reload,
	 * and all destination page initialization. Use the exact base-menu startup
	 * sequence rather than delegating to a page-specific helper. */
	if (menu_restore_frontend_music_pending != 0 && !menu.page_swap &&
	    menu.page != MenuPage_Stage && menu.page != MenuPage_Freeplay &&
	    menu.page != MenuPage_CharacterSelect && menu.next_page == menu.page)
	{
		if (menu_restore_frontend_music_pending > 1)
			menu_restore_frontend_music_pending--;
		else
		{
			Audio_StopXA();
			Audio_PlayXA_Track(XA_GettinFreaky, 0x40, 0, true);
			Audio_WaitPlayXA();
			stage.song_step = 0;
			menu_restore_frontend_music_pending = 0;
		}
	}
}'''
    text = replace_once(text, tail, tail_new, "M3 stable-frame tail restore")
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
    if "M1_STR_DIAGNOSTIC_V3" not in strplay:
        raise SystemExit("M1 v3 diagnostic STR player missing")
    if "[M1V3 E3] no first STR frame" not in strplay:
        raise SystemExit("M1 v3 first-frame diagnostic missing")
    if "static boolean strKickCD" not in strplay or "static boolean strNextVlc" not in strplay:
        raise SystemExit("M1 v3 bounded STR helpers missing")
    if "CdSearchFile(&file, str->FileName)" in strplay:
        raise SystemExit("raw CdSearchFile survived inside STR player")
    if "Menu_SyncV084Textures" in menu:
        if "M3_STABLE_FRAME_AUDIO_RESTORE_V3" not in menu:
            raise SystemExit("M3 v3 stable-frame restore marker missing")
        if "menu_restore_frontend_music_pending = 2" not in menu:
            raise SystemExit("M3 v3 transition pending flag missing")
        if "Audio_PlayXA_Track(XA_GettinFreaky, 0x40, 0, true);" not in menu:
            raise SystemExit("M3 v3 direct Gettin' Freaky restart missing")
    print("Applied/validated ISO9660, diagnostic STR v3, and stable-frame frontend audio v3")


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
