#ifndef FNF_PS2_STORY_CATALOG_H
#define FNF_PS2_STORY_CATALOG_H

#include "fixed.h"
#include <stddef.h>

#define STORY_LEVEL_VISIBLE (1u << 0)

typedef struct StoryLevelRecord {
    u32 id_offset;
    u32 name_offset;
    u32 title_asset_offset;
    u32 song_start;
    u16 song_count;
    u16 flags;
    u32 background;
    u32 reserved;
} __attribute__((packed)) StoryLevelRecord;

typedef struct StoryLevelEntry {
    const char *id;
    const char *name;
    const char *title_asset;
    u16 song_count;
    u16 flags;
    u32 background;
} StoryLevelEntry;

typedef struct StoryCatalog {
    void *blob;
    size_t blob_size;
    StoryLevelRecord *levels;
    u32 *song_offsets;
    char *strings;
    u32 string_bytes;
    u32 song_ref_count;
    u16 level_count;
    boolean loaded;
} StoryCatalog;

boolean StoryCatalog_Load(StoryCatalog *catalog, const char *path);
void StoryCatalog_Free(StoryCatalog *catalog);
boolean StoryCatalog_GetLevel(
    const StoryCatalog *catalog,
    u16 index,
    StoryLevelEntry *entry);
const char *StoryCatalog_GetSong(
    const StoryCatalog *catalog,
    u16 level_index,
    u16 song_index);

#endif
