#ifndef FNF_PS2_SONG_CATALOG_H
#define FNF_PS2_SONG_CATALOG_H

#include "fixed.h"
#include <stddef.h>

typedef struct SongCatalogRecord {
    u32 song_id_offset;
    u32 display_name_offset;
    u32 variation_offset;
    u32 difficulty_offset;
    u32 descriptor_path_offset;
} __attribute__((packed)) SongCatalogRecord;

typedef struct SongCatalogEntry {
    const char *song_id;
    const char *display_name;
    const char *variation;
    const char *difficulty;
    const char *descriptor_path;
} SongCatalogEntry;

typedef struct SongCatalog {
    void *blob;
    size_t blob_size;
    SongCatalogRecord *records;
    char *strings;
    u32 string_bytes;
    u32 count;
    boolean loaded;
} SongCatalog;

boolean SongCatalog_Load(SongCatalog *catalog, const char *path);
void SongCatalog_Free(SongCatalog *catalog);
boolean SongCatalog_Get(const SongCatalog *catalog, u32 index, SongCatalogEntry *entry);
boolean SongCatalog_Find(
    const SongCatalog *catalog,
    const char *song_id,
    const char *variation,
    const char *difficulty,
    SongCatalogEntry *entry);

#endif
