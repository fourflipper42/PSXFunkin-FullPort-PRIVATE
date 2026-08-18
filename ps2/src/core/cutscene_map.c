#include "cutscene_map.h"

#include "mem.h"
#include <string.h>

typedef struct CutsceneMapHeader {
    char magic[4];
    u16 version;
    u16 count;
    u32 entry_size;
    u32 string_bytes;
} __attribute__((packed)) CutsceneMapHeader;

#define CUTSCENE_MAP_VERSION 1

static const char *map_string(const CutsceneMap *map, u32 offset)
{
    if (map == NULL || !map->loaded || offset >= map->string_bytes)
        return NULL;
    return map->strings + offset;
}

boolean CutsceneMap_Load(CutsceneMap *map, const char *path)
{
    AssetFile file;
    CutsceneMapHeader *header;
    size_t entries_bytes;
    size_t minimum;
    size_t got;
    u16 i;

    if (map == NULL || path == NULL)
        return false;
    memset(map, 0, sizeof(*map));
    memset(&file, 0, sizeof(file));
    if (!AssetFile_Open(&file, path))
        return false;

    map->blob_size = AssetFile_Size(&file);
    if (map->blob_size < sizeof(CutsceneMapHeader))
        goto fail;
    map->blob = Mem_Alloc(map->blob_size);
    if (map->blob == NULL)
        goto fail;
    got = AssetFile_Read(&file, map->blob, map->blob_size);
    AssetFile_Close(&file);
    if (got != map->blob_size)
        goto fail;

    header = (CutsceneMapHeader *)map->blob;
    if (memcmp(header->magic, "FCMP", 4) != 0 ||
        header->version != CUTSCENE_MAP_VERSION ||
        header->entry_size != sizeof(CutsceneMapEntry))
        goto fail;

    entries_bytes = (size_t)header->count * sizeof(CutsceneMapEntry);
    minimum = sizeof(CutsceneMapHeader) + entries_bytes + header->string_bytes;
    if (minimum > map->blob_size)
        goto fail;

    map->entries = (CutsceneMapEntry *)((u8 *)map->blob + sizeof(CutsceneMapHeader));
    map->strings = (char *)((u8 *)map->entries + entries_bytes);
    map->count = header->count;
    map->string_bytes = header->string_bytes;
    map->loaded = true;

    for (i = 0; i < map->count; ++i) {
        if (map_string(map, map->entries[i].song_offset) == NULL ||
            map_string(map, map->entries[i].cutscene_offset) == NULL)
            goto fail;
    }
    return true;

fail:
    AssetFile_Close(&file);
    CutsceneMap_Free(map);
    return false;
}

void CutsceneMap_Free(CutsceneMap *map)
{
    if (map == NULL)
        return;
    if (map->blob != NULL)
        Mem_Free(map->blob);
    memset(map, 0, sizeof(*map));
}

boolean CutsceneMap_FindPreSong(
    const CutsceneMap *map,
    const char *song_id,
    boolean story_mode,
    const char **cutscene_id)
{
    u16 i;
    if (cutscene_id != NULL)
        *cutscene_id = NULL;
    if (map == NULL || !map->loaded || song_id == NULL)
        return false;

    for (i = 0; i < map->count; ++i) {
        const CutsceneMapEntry *entry = &map->entries[i];
        const char *mapped_song;
        if (!(entry->flags & CUTSCENE_MAP_FLAG_PRESONG))
            continue;
        if ((entry->flags & CUTSCENE_MAP_FLAG_STORY_ONLY) && !story_mode)
            continue;
        mapped_song = map_string(map, entry->song_offset);
        if (mapped_song != NULL && strcmp(mapped_song, song_id) == 0) {
            if (cutscene_id != NULL)
                *cutscene_id = map_string(map, entry->cutscene_offset);
            return true;
        }
    }
    return false;
}
