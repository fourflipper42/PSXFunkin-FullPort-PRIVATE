#include "song_catalog.h"

#include "asset_file.h"
#include "mem.h"
#include <string.h>

typedef struct SongCatalogHeader {
    char magic[4];
    u16 version;
    u16 flags;
    u32 count;
    u32 record_size;
    u32 string_bytes;
} __attribute__((packed)) SongCatalogHeader;

#define SONG_CATALOG_VERSION 1

static const char *catalog_string(const SongCatalog *catalog, u32 offset)
{
    const char *value;
    size_t remaining;

    if (catalog == NULL || catalog->strings == NULL || offset >= catalog->string_bytes)
        return NULL;
    value = catalog->strings + offset;
    remaining = catalog->string_bytes - offset;
    if (memchr(value, '\0', remaining) == NULL)
        return NULL;
    return value;
}

boolean SongCatalog_Load(SongCatalog *catalog, const char *path)
{
    AssetFile file;
    SongCatalogHeader *header;
    size_t records_bytes;
    size_t minimum;
    size_t got;
    u32 i;

    if (catalog == NULL || path == NULL)
        return false;

    memset(catalog, 0, sizeof(*catalog));
    memset(&file, 0, sizeof(file));
    if (!AssetFile_Open(&file, path))
        return false;

    catalog->blob_size = AssetFile_Size(&file);
    if (catalog->blob_size < sizeof(SongCatalogHeader))
        goto fail;

    catalog->blob = Mem_Alloc(catalog->blob_size);
    if (catalog->blob == NULL)
        goto fail;
    got = AssetFile_Read(&file, catalog->blob, catalog->blob_size);
    AssetFile_Close(&file);
    if (got != catalog->blob_size)
        goto fail;

    header = (SongCatalogHeader *)catalog->blob;
    if (memcmp(header->magic, "FCAT", 4) != 0 ||
        header->version != SONG_CATALOG_VERSION ||
        header->record_size != sizeof(SongCatalogRecord))
        goto fail;

    records_bytes = (size_t)header->count * sizeof(SongCatalogRecord);
    if (header->count != 0 && records_bytes / sizeof(SongCatalogRecord) != header->count)
        goto fail;
    minimum = sizeof(SongCatalogHeader) + records_bytes + (size_t)header->string_bytes;
    if (minimum > catalog->blob_size)
        goto fail;

    catalog->records = (SongCatalogRecord *)((u8 *)catalog->blob + sizeof(SongCatalogHeader));
    catalog->strings = (char *)catalog->records + records_bytes;
    catalog->string_bytes = header->string_bytes;
    catalog->count = header->count;

    for (i = 0; i < catalog->count; ++i) {
        const SongCatalogRecord *record = &catalog->records[i];
        if (catalog_string(catalog, record->song_id_offset) == NULL ||
            catalog_string(catalog, record->display_name_offset) == NULL ||
            catalog_string(catalog, record->variation_offset) == NULL ||
            catalog_string(catalog, record->difficulty_offset) == NULL ||
            catalog_string(catalog, record->descriptor_path_offset) == NULL)
            goto fail;
    }

    catalog->loaded = true;
    return true;

fail:
    AssetFile_Close(&file);
    SongCatalog_Free(catalog);
    return false;
}

void SongCatalog_Free(SongCatalog *catalog)
{
    if (catalog == NULL)
        return;
    if (catalog->blob != NULL)
        Mem_Free(catalog->blob);
    memset(catalog, 0, sizeof(*catalog));
}

boolean SongCatalog_Get(const SongCatalog *catalog, u32 index, SongCatalogEntry *entry)
{
    const SongCatalogRecord *record;

    if (catalog == NULL || !catalog->loaded || entry == NULL || index >= catalog->count)
        return false;

    record = &catalog->records[index];
    entry->song_id = catalog_string(catalog, record->song_id_offset);
    entry->display_name = catalog_string(catalog, record->display_name_offset);
    entry->variation = catalog_string(catalog, record->variation_offset);
    entry->difficulty = catalog_string(catalog, record->difficulty_offset);
    entry->descriptor_path = catalog_string(catalog, record->descriptor_path_offset);
    return entry->song_id != NULL && entry->display_name != NULL &&
        entry->variation != NULL && entry->difficulty != NULL &&
        entry->descriptor_path != NULL;
}
