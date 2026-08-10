#!/usr/bin/env python3
"""Patch PSXFunkin's CD lookup so large ISO9660 directories work on PS1.

PsyQ CdSearchFile is kept as the fast path. If it misses, the fallback reads the
ISO9660 primary volume descriptor and scans every sector of each directory in
the requested path. This is needed by the full port because directories such as
MENU, CHAR, and WEEK10 are now larger than the original one-sector layout.
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
 * contains ISO9660 directories spanning multiple 2048-byte sectors.  Some
 * PsyQ revisions fail to find records beyond the first directory sector.
 *
 * This small fallback reads ISO9660 metadata directly only after CdSearchFile
 * misses.  It understands the subset used by mkpsxiso: primary volume
 * descriptor, nested directories, and ordinary ISO9660 file records.
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

			/* A zero record length pads the rest of this logical sector. */
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

	/* ISO9660 Primary Volume Descriptor is logical sector 16. */
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

void IO_FindFile(CdlFILE *file, const char *path)
{
	printf("[IO_FindFile] Searching for %s\n", path);
	
	//Stop XA playback
	Audio_StopXA();
	
	//Use PsyQ's cached search first, then scan the complete ISO9660 directory.
	if (!CdSearchFile(file, (char*)path))
	{
		printf("[IO_FindFile] CdSearchFile miss, using full ISO9660 scan\n");
		if (!IO_ISOSearchFile(file, path))
		{
			sprintf(error_msg, "[IO_FindFile] %s not found", path);
			ErrorLock();
		}
	}
}
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()

    path = args.upstream / "src" / "io.c"
    text = path.read_text()
    count = text.count(OLD)
    if count != 1:
        raise SystemExit(f"IO_FindFile baseline anchor changed: expected 1, found {count}")
    path.write_text(text.replace(OLD, NEW, 1))

    patched = path.read_text()
    required = (
        "IO_ISOSearchFile",
        "IO_ISOFindInDirectory",
        "IO_ReadISOSector(16)",
        "CdSearchFile(file, (char*)path)",
        "CdIntToPos(extent, &file->pos)",
    )
    for marker in required:
        if marker not in patched:
            raise SystemExit(f"ISO9660 fallback marker missing: {marker}")
    print("Applied full-directory ISO9660 lookup fallback")


if __name__ == "__main__":
    main()
