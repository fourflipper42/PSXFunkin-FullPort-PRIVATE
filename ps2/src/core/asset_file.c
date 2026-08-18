#include "asset_file.h"

#include <string.h>

static boolean is_disc_path(const char *path)
{
    return path != NULL &&
        (path[0] == '\\' || strncmp(path, "cdrom0:", 7) == 0);
}

boolean AssetFile_Open(AssetFile *file, const char *path)
{
    long end;
    const char *disc_path;

    if (file == NULL || path == NULL)
        return false;

    memset(file, 0, sizeof(*file));

    if (is_disc_path(path)) {
        disc_path = path;
        if (strncmp(path, "cdrom0:", 7) == 0)
            disc_path = path + 7;
        if (!Disc_Open(&file->disc, disc_path))
            return false;
        file->backend = ASSET_FILE_DISC;
        file->size = Disc_Size(&file->disc);
        return true;
    }

    file->host = fopen(path, "rb");
    if (file->host == NULL)
        return false;

    if (fseek(file->host, 0, SEEK_END) != 0) {
        fclose(file->host);
        memset(file, 0, sizeof(*file));
        return false;
    }
    end = ftell(file->host);
    if (end < 0 || (unsigned long)end > 0xFFFFFFFFUL ||
        fseek(file->host, 0, SEEK_SET) != 0) {
        fclose(file->host);
        memset(file, 0, sizeof(*file));
        return false;
    }

    file->backend = ASSET_FILE_HOST;
    file->size = (u32)end;
    return true;
}

void AssetFile_Close(AssetFile *file)
{
    if (file == NULL)
        return;

    if (file->backend == ASSET_FILE_HOST && file->host != NULL)
        fclose(file->host);
    else if (file->backend == ASSET_FILE_DISC)
        Disc_Close(&file->disc);

    memset(file, 0, sizeof(*file));
}

size_t AssetFile_Read(AssetFile *file, void *dst, size_t bytes)
{
    if (file == NULL || dst == NULL || bytes == 0)
        return 0;

    if (file->backend == ASSET_FILE_HOST && file->host != NULL)
        return fread(dst, 1, bytes, file->host);
    if (file->backend == ASSET_FILE_DISC)
        return Disc_Read(&file->disc, dst, bytes);
    return 0;
}

boolean AssetFile_Seek(AssetFile *file, u32 offset)
{
    if (file == NULL || offset > file->size)
        return false;

    if (file->backend == ASSET_FILE_HOST && file->host != NULL) {
        if (offset > 0x7FFFFFFFu)
            return false;
        if (fseek(file->host, (long)offset, SEEK_SET) != 0)
            return false;
        clearerr(file->host);
        return true;
    }
    if (file->backend == ASSET_FILE_DISC)
        return Disc_Seek(&file->disc, offset);
    return false;
}

u32 AssetFile_Tell(const AssetFile *file)
{
    long pos;

    if (file == NULL)
        return 0;
    if (file->backend == ASSET_FILE_DISC)
        return Disc_Tell(&file->disc);
    if (file->backend != ASSET_FILE_HOST || file->host == NULL)
        return 0;

    pos = ftell(file->host);
    if (pos < 0)
        return 0;
    return (u32)pos;
}

u32 AssetFile_Size(const AssetFile *file)
{
    return file != NULL ? file->size : 0;
}

boolean AssetFile_IsOpen(const AssetFile *file)
{
    return file != NULL && file->backend != ASSET_FILE_NONE;
}
