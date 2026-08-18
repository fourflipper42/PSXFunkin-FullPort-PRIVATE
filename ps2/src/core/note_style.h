#ifndef FNF_PS2_NOTE_STYLE_H
#define FNF_PS2_NOTE_STYLE_H

#include "sprite_atlas.h"

typedef enum ReceptorVisualState {
    RECEPTOR_STATIC = 0,
    RECEPTOR_PRESS = 1,
    RECEPTOR_CONFIRM = 2,
    RECEPTOR_CONFIRM_HOLD = 3
} ReceptorVisualState;

typedef struct NoteStyle {
    void *blob;
    size_t blob_size;
    char *strings;
    u32 string_bytes;
    const char *note_prefix[4];
    const char *strum_static_prefix[4];
    const char *strum_press_prefix[4];
    const char *strum_confirm_prefix[4];
    const char *strum_confirm_hold_prefix[4];
    SpriteAtlas note_atlas;
    SpriteAtlas strum_atlas;
    TextureAsset hold_texture;
    float note_scale;
    float strum_scale;
    float hold_scale;
    float strum_offset_x;
    float strum_offset_y;
    float hold_offset_x;
    float hold_offset_y;
    u16 flags;
    boolean loaded;
} NoteStyle;

boolean NoteStyle_Load(GSGLOBAL *gs, NoteStyle *style, const char *base_path);
void NoteStyle_Free(NoteStyle *style);

void NoteStyle_DrawTap(
    GSGLOBAL *gs,
    const NoteStyle *style,
    u8 lane,
    float center_x,
    float center_y,
    int z,
    u64 color);

void NoteStyle_DrawReceptor(
    GSGLOBAL *gs,
    const NoteStyle *style,
    u8 lane,
    ReceptorVisualState state,
    u32 animation_tick,
    float center_x,
    float center_y,
    int z,
    u64 color);

void NoteStyle_DrawHoldPiece(
    GSGLOBAL *gs,
    const NoteStyle *style,
    u8 lane,
    float center_x,
    float top_y,
    float height,
    boolean end_cap,
    int z,
    u64 color);

#endif
