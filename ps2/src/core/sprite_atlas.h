#ifndef FNF_PS2_SPRITE_ATLAS_H
#define FNF_PS2_SPRITE_ATLAS_H

#include "texture_asset.h"

typedef struct AtlasFrame {
    u32 name_offset;
    u16 x;
    u16 y;
    u16 width;
    u16 height;
    s16 frame_x;
    s16 frame_y;
    u16 frame_width;
    u16 frame_height;
    u16 flags;
    u16 page_index;
} __attribute__((packed)) AtlasFrame;

typedef struct SpriteAtlas {
    TextureAsset *textures;
    void *frame_blob;
    size_t frame_blob_size;
    AtlasFrame *frames;
    char *strings;
    u16 frame_count;
    u16 texture_count;
    boolean loaded;
} SpriteAtlas;

boolean SpriteAtlas_Load(
    GSGLOBAL *gs,
    SpriteAtlas *atlas,
    const char *texture_path,
    const char *frames_path,
    boolean linear_filter);
void SpriteAtlas_Forget(SpriteAtlas *atlas);
const char *SpriteAtlas_FrameName(const SpriteAtlas *atlas, u16 frame_index);
s32 SpriteAtlas_FindExact(const SpriteAtlas *atlas, const char *name);
u16 SpriteAtlas_CountPrefix(const SpriteAtlas *atlas, const char *prefix);
s32 SpriteAtlas_FindPrefixNth(const SpriteAtlas *atlas, const char *prefix, u16 nth);
void SpriteAtlas_DrawFrameEx(
    GSGLOBAL *gs,
    const SpriteAtlas *atlas,
    u16 frame_index,
    float x,
    float y,
    float scale_x,
    float scale_y,
    boolean flip_x,
    boolean flip_y,
    int z,
    u64 color);
void SpriteAtlas_DrawFrame(
    GSGLOBAL *gs,
    const SpriteAtlas *atlas,
    u16 frame_index,
    float x,
    float y,
    float scale_x,
    float scale_y,
    int z,
    u64 color);

#endif
