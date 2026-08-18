#ifndef FNF_PS2_CUTSCENE_MAP_H
#define FNF_PS2_CUTSCENE_MAP_H

#include "asset_file.h"

#define CUTSCENE_MAP_FLAG_PRESONG     (1u << 0)
#define CUTSCENE_MAP_FLAG_STORY_ONLY  (1u << 1)
#define CUTSCENE_MAP_FLAG_POSTSONG    (1u << 2)

typedef struct CutsceneMapEntry {
    u32 song_offset;
    u32 cutscene_offset;
    u32 flags;
} __attribute__((packed)) CutsceneMapEntry;

typedef struct CutsceneMap {
    void *blob;
    size_t blob_size;
    CutsceneMapEntry *entries;
    char *strings;
    u16 count;
    u32 string_bytes;
    boolean loaded;
} CutsceneMap;

boolean CutsceneMap_Load(CutsceneMap *map, const char *path);
void CutsceneMap_Free(CutsceneMap *map);
boolean CutsceneMap_FindPreSong(
    const CutsceneMap *map,
    const char *song_id,
    boolean story_mode,
    const char **cutscene_id);
boolean CutsceneMap_FindPostSong(
    const CutsceneMap *map,
    const char *song_id,
    boolean story_mode,
    const char **cutscene_id);

#endif
