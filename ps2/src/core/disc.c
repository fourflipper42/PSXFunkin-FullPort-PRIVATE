#include "disc.h"

#include <libcdvd.h>
#include <stdint.h>
#include <string.h>

#define DISC_SECTOR_SIZE 2048u
#define DISC_DIRECT_MAX_SECTORS 16u

static u8 sector_scratch[DISC_SECTOR_SIZE] __attribute__((aligned(64)));
static sceCdRMode read_mode;
static boolean disc_ready;

static boolean Disc_ReadSectors(u32 lsn, u32 sectors, void *dst)
{
    if (sectors == 0)
        return true;
    if (!sceCdRead(lsn, sectors, dst, &read_mode))
        return false;
    sceCdSync(0);
    return sceCdGetError() == SCECdErNO;
}

boolean Disc_Init(void)
{
    memset(&read_mode, 0, sizeof(read_mode));
    read_mode.trycount = 16;
    read_mode.spindlctrl = SCECdSpinStm;
    read_mode.datapattern = SCECdSecS2048;

    disc_ready = false;
    if (!sceCdInit(SCECdINIT))
        return false;
    if (sceCdDiskReady(0) != SCECdComplete)
        return false;

    disc_ready = true;
    return true;
}

boolean Disc_Open(DiscFile *file, const char *iso_path)
{
    sceCdlFILE found;

    if (file == NULL || iso_path == NULL || !disc_ready)
        return false;

    memset(file, 0, sizeof(*file));
    memset(&found, 0, sizeof(found));
    if (!sceCdSearchFile(&found, iso_path))
        return false;

    file->lsn = found.lsn;
    file->size = found.size;
    file->pos = 0;
    file->open = true;
    return true;
}

void Disc_Close(DiscFile *file)
{
    if (file != NULL)
        memset(file, 0, sizeof(*file));
}

size_t Disc_Read(DiscFile *file, void *dst, size_t bytes)
{
    u8 *out = (u8 *)dst;
    size_t total = 0;

    if (file == NULL || !file->open || dst == NULL || bytes == 0)
        return 0;

    if (file->pos >= file->size)
        return 0;
    if (bytes > (size_t)(file->size - file->pos))
        bytes = (size_t)(file->size - file->pos);

    while (bytes > 0) {
        u32 sector_index = file->pos / DISC_SECTOR_SIZE;
        u32 in_sector = file->pos % DISC_SECTOR_SIZE;
        size_t file_left = (size_t)(file->size - file->pos);

        /* Fast path: contiguous full sectors directly into an aligned EE buffer. */
        if (in_sector == 0 && bytes >= DISC_SECTOR_SIZE &&
            (((uintptr_t)out & 63u) == 0)) {
            u32 sectors = (u32)(bytes / DISC_SECTOR_SIZE);
            u32 full_file_sectors = (u32)(file_left / DISC_SECTOR_SIZE);
            size_t moved;

            if (sectors > full_file_sectors)
                sectors = full_file_sectors;
            if (sectors > DISC_DIRECT_MAX_SECTORS)
                sectors = DISC_DIRECT_MAX_SECTORS;

            if (sectors > 0) {
                if (!Disc_ReadSectors(file->lsn + sector_index, sectors, out))
                    break;
                moved = (size_t)sectors * DISC_SECTOR_SIZE;
                file->pos += (u32)moved;
                out += moved;
                bytes -= moved;
                total += moved;
                continue;
            }
        }

        /* Tail/unaligned path: read one sector and copy only requested bytes. */
        if (!Disc_ReadSectors(file->lsn + sector_index, 1, sector_scratch))
            break;
        {
            size_t moved = DISC_SECTOR_SIZE - in_sector;
            if (moved > bytes)
                moved = bytes;
            if (moved > file_left)
                moved = file_left;
            memcpy(out, sector_scratch + in_sector, moved);
            file->pos += (u32)moved;
            out += moved;
            bytes -= moved;
            total += moved;
        }
    }

    return total;
}

boolean Disc_Seek(DiscFile *file, u32 offset)
{
    if (file == NULL || !file->open || offset > file->size)
        return false;
    file->pos = offset;
    return true;
}

u32 Disc_Tell(const DiscFile *file)
{
    return (file != NULL && file->open) ? file->pos : 0;
}

u32 Disc_Size(const DiscFile *file)
{
    return (file != NULL && file->open) ? file->size : 0;
}
