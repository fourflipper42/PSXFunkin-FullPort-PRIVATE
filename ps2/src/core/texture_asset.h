#ifndef FNF_PS2_TEXTURE_ASSET_H
#define FNF_PS2_TEXTURE_ASSET_H

#include "asset_file.h"
#include <gsKit.h>

typedef struct TextureAsset {
    GSTEXTURE texture;
    boolean loaded;
} TextureAsset;

/* Initialize after gsKit_init_screen(), once the frame buffers own their GS
 * memory. Remaining VRAM becomes a cache for FNF textures kept in EE RAM. */
void TextureAsset_InitStreaming(GSGLOBAL *gs);
void TextureAsset_EndFrame(GSGLOBAL *gs);

boolean TextureAsset_Load(GSGLOBAL *gs, TextureAsset *asset, const char *path, boolean linear_filter);
void TextureAsset_Forget(TextureAsset *asset);
void TextureAsset_ClearVRAM(GSGLOBAL *gs);

/* All FNF artwork is authored against the canonical 640x360 logical canvas.
 * Configure this once when the output aspect mode changes so stage props,
 * characters, atlases and UI textures land in the same physical region as
 * untextured gameplay primitives. */
void TextureAsset_SetDrawTransform(
    float x_scale,
    float y_scale,
    float x_offset,
    float y_offset);

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
