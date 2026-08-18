#include "story_catalog.h"

#include "asset_file.h"
#include "mem.h"
#include <string.h>

typedef struct StoryCatalogHeader {
    char magic[4];
    u16 version;
    u16 level_count;
    u32 level_record_size;
    u32 song_ref_count;
    u32 string_bytes;
    u32 reserved;
} __attribute__((packed)) StoryCatalogHeader;

#define STORY_CATALOG_VERSION 1

static const char *story_string(const StoryCatalog *catalog, u32 offset)
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

boolean StoryCatalog_Load(StoryCatalog *catalog, const char *path)
{
    AssetFile file;
    StoryCatalogHeader *header;
    size_t levels_bytes;
    size_t songs_bytes;
    size_t minimum;
    size_t got;
    u16 i;
    u32 j;

    if (catalog == NULL || path == NULL)
        return false;

    memset(catalog, 0, sizeof(*catalog));
    memset(&file, 0, sizeof(file));
    if (!AssetFile_Open(&file, path))
        return false;

    catalog->blob_size = AssetFile_Size(&file);
    if (catalog->blob_size < sizeof(StoryCatalogHeader))
        goto fail;

    catalog->blob = Mem_Alloc(catalog->blob_size);
    if (catalog->blob == NULL)
        goto fail;
    got = AssetFile_Read(&file, catalog->blob, catalog->blob_size);
    AssetFile_Close(&file);
    if (got != catalog->blob_size)
        goto fail;

    header = (StoryCatalogHeader *)catalog->blob;
    if (memcmp(header->magic, "FSTY", 4) != 0 ||
        header->version != STORY_CATALOG_VERSION ||
        header->level_record_size != sizeof(StoryLevelRecord))
        goto fail;

    levels_bytes = (size_t)header->level_count * sizeof(StoryLevelRecord);
    songs_bytes = (size_t)header->song_ref_count * sizeof(u32);
    minimum = sizeof(StoryCatalogHeader) + levels_bytes + songs_bytes +
        (size_t)header->string_bytes;
    if (minimum > catalog->blob_size)
        goto fail;

    catalog->levels = (StoryLevelRecord *)((u8 *)catalog->blob + sizeof(StoryCatalogHeader));
    catalog->song_offsets = (u32 *)((u8 *)catalog->levels + levels_bytes);
    catalog->strings = (char *)catalog->song_offsets + songs_bytes;
    catalog->string_bytes = header->string_bytes;
    catalog->song_ref_count = header->song_ref_count;
    catalog->level_count = header->level_count;

    for (i = 0; i < catalog->level_count; ++i) {
        const StoryLevelRecord *level = &catalog->levels[i];
        u32 end = level->song_start + level->song_count;
        if (end < level->song_start || end > catalog->song_ref_count ||
            story_string(catalog, level->id_offset) == NULL ||
            story_string(catalog, level->name_offset) == NULL ||
            story_string(catalog, level->title_asset_offset) == NULL)
            goto fail;
    }
    for (j = 0; j < catalog->song_ref_count; ++j) {
        if (story_string(catalog, catalog->song_offsets[j]) == NULL)
            goto fail;
    }

    catalog->loaded = true;
    return true;

fail:
    AssetFile_Close(&file);
    StoryCatalog_Free(catalog);
    return false;
}

void StoryCatalog_Free(StoryCatalog *catalog)
{
    if (catalog == NULL)
        return;
    if (catalog->blob != NULL)
        Mem_Free(catalog->blob);
    memset(catalog, 0, sizeof(*catalog));
}

boolean StoryCatalog_GetLevel(
    const StoryCatalog *catalog,
    u16 index,
    StoryLevelEntry *entry)
{
    const StoryLevelRecord *record;

    if (catalog == NULL || !catalog->loaded || entry == NULL || index >= catalog->level_count)
        return false;

    record = &catalog->levels[index];
    entry->id = story_string(catalog, record->id_offset);
    entry->name = story_string(catalog, record->name_offset);
    entry->title_asset = story_string(catalog, record->title_asset_offset);
    entry->song_count = record->song_count;
    entry->flags = record->flags;
    entry->background = record->background;
    return entry->id != NULL && entry->name != NULL && entry->title_asset != NULL;
}

const char *StoryCatalog_GetSong(
    const StoryCatalog *catalog,
    u16 level_index,
    u16 song_index)
{
    const StoryLevelRecord *level;
    u32 reference;

    if (catalog == NULL || !catalog->loaded || level_index >= catalog->level_count)
        return NULL;
    level = &catalog->levels[level_index];
    if (song_index >= level->song_count)
        return NULL;
    reference = level->song_start + song_index;
    if (reference >= catalog->song_ref_count)
        return NULL;
    return story_string(catalog, catalog->song_offsets[reference]);
}
