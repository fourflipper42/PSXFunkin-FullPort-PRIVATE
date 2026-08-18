#ifndef FNF_PS2_SONG_DESCRIPTOR_H
#define FNF_PS2_SONG_DESCRIPTOR_H

#include "fixed.h"
#include <stddef.h>

typedef struct SongDescriptor {
    void *blob;
    size_t blob_size;
    char *strings;
    u32 string_bytes;

    const char *song_id;
    const char *display_name;
    const char *variation;
    const char *difficulty;
    const char *stage;
    const char *note_style;
    const char *player;
    const char *girlfriend;
    const char *opponent;
    const char *instrumental;
    fixed_t scroll_speed;
    boolean loaded;
} SongDescriptor;

typedef struct SongAssetPaths {
    char chart[256];
    char events[256];
    char inst[256];
    char voices[256];
    char stage_base[256];
    char note_style_base[256];
    char player_base[256];
    char girlfriend_base[256];
    char opponent_base[256];
} SongAssetPaths;

boolean SongDescriptor_Load(SongDescriptor *song, const char *path);
void SongDescriptor_Free(SongDescriptor *song);
boolean SongDescriptor_BuildDiscPaths(const SongDescriptor *song, SongAssetPaths *paths);
void SongDescriptor_CharacterFile(
    char *out,
    size_t out_size,
    const char *character_base,
    const char *filename);

#endif
