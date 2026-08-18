#ifndef FNF_PS2_TEXTURE_ASSET_H
#define FNF_PS2_TEXTURE_ASSET_H

#include "asset_file.h"
#include <gsKit.h>

typedef struct TextureAsset {
    GSTEXTURE texture;
    boolean loaded;
} TextureAsset;

boolean TextureAsset_Load(GSGLOBAL *gs, TextureAsset *asset, const char *path, boolean linear_filter);
void TextureAsset_Forget(TextureAsset *asset);
void TextureAsset_ClearVRAM(GSGLOBAL *gs);
void TextureAsset_Draw(
    GSGLOBAL *gs,
    const TextureAsset *asset,
    float x1,
    float y1,
    float x2,
    float y2,
    float u1,
    float v1,
    float u2,
    float v2,
    int z,
    u64 color);

#endif
