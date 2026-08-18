#include "sprite_atlas.h"

#include "asset_file.h"
#include "mem.h"
#include <string.h>

typedef struct AtlasHeader {
    char magic[4];
    u16 version;
    u16 frame_count;
    u32 string_bytes;
    u32 record_size;
} __attribute__((packed)) AtlasHeader;

#define ATLAS_VERSION 1

static boolean starts_with(const char *text, const char *prefix)
{
    size_t n;
    if (text == NULL || prefix == NULL)
        return false;
    n = strlen(prefix);
    return strncmp(text, prefix, n) == 0;
}

boolean SpriteAtlas_Load(
    GSGLOBAL *gs,
    SpriteAtlas *atlas,
    const char *texture_path,
    const char *frames_path,
    boolean linear_filter)
{
    AssetFile file;
    AtlasHeader *header;
    size_t minimum;
    size_t got;

    if (gs == NULL || atlas == NULL || texture_path == NULL || frames_path == NULL)
        return false;

    memset(atlas, 0, sizeof(*atlas));
    memset(&file, 0, sizeof(file));

    if (!TextureAsset_Load(gs, &atlas->texture, texture_path, linear_filter))
        return false;

    if (!AssetFile_Open(&file, frames_path))
        goto fail;
    atlas->frame_blob_size = AssetFile_Size(&file);
    if (atlas->frame_blob_size < sizeof(AtlasHeader))
        goto fail;

    atlas->frame_blob = Mem_Alloc(atlas->frame_blob_size);
    if (atlas->frame_blob == NULL)
        goto fail;
    got = AssetFile_Read(&file, atlas->frame_blob, atlas->frame_blob_size);
    AssetFile_Close(&file);
    if (got != atlas->frame_blob_size)
        goto fail;

    header = (AtlasHeader *)atlas->frame_blob;
    if (memcmp(header->magic, "FATL", 4) != 0 ||
        header->version != ATLAS_VERSION ||
        header->frame_count == 0 ||
        header->record_size != sizeof(AtlasFrame))
        goto fail;

    minimum = sizeof(AtlasHeader) +
        ((size_t)header->frame_count * sizeof(AtlasFrame)) +
        header->string_bytes;
    if (minimum > atlas->frame_blob_size)
        goto fail;

    atlas->frames = (AtlasFrame *)((u8 *)atlas->frame_blob + sizeof(AtlasHeader));
    atlas->strings = (char *)(atlas->frames + header->frame_count);
    atlas->frame_count = header->frame_count;
    atlas->loaded = true;
    return true;

fail:
    AssetFile_Close(&file);
    if (atlas->frame_blob != NULL)
        Mem_Free(atlas->frame_blob);
    atlas->frame_blob = NULL;
    TextureAsset_Forget(&atlas->texture);
    memset(atlas, 0, sizeof(*atlas));
    return false;
}

void SpriteAtlas_Forget(SpriteAtlas *atlas)
{
    if (atlas == NULL)
        return;
    if (atlas->frame_blob != NULL)
        Mem_Free(atlas->frame_blob);
    TextureAsset_Forget(&atlas->texture);
    memset(atlas, 0, sizeof(*atlas));
}

const char *SpriteAtlas_FrameName(const SpriteAtlas *atlas, u16 frame_index)
{
    u32 offset;
    if (atlas == NULL || !atlas->loaded || frame_index >= atlas->frame_count)
        return NULL;
    offset = atlas->frames[frame_index].name_offset;
    if (offset >= atlas->frame_blob_size)
        return NULL;
    return atlas->strings + offset;
}

s32 SpriteAtlas_FindExact(const SpriteAtlas *atlas, const char *name)
{
    u16 i;
    if (atlas == NULL || !atlas->loaded || name == NULL)
        return -1;
    for (i = 0; i < atlas->frame_count; ++i) {
        const char *frame_name = SpriteAtlas_FrameName(atlas, i);
        if (frame_name != NULL && strcmp(frame_name, name) == 0)
            return (s32)i;
    }
    return -1;
}

u16 SpriteAtlas_CountPrefix(const SpriteAtlas *atlas, const char *prefix)
{
    u16 i;
    u16 count = 0;
    if (atlas == NULL || !atlas->loaded || prefix == NULL)
        return 0;
    for (i = 0; i < atlas->frame_count; ++i) {
        const char *name = SpriteAtlas_FrameName(atlas, i);
        if (starts_with(name, prefix))
            ++count;
    }
    return count;
}

s32 SpriteAtlas_FindPrefixNth(const SpriteAtlas *atlas, const char *prefix, u16 nth)
{
    u16 i;
    u16 seen = 0;
    if (atlas == NULL || !atlas->loaded || prefix == NULL)
        return -1;
    for (i = 0; i < atlas->frame_count; ++i) {
        const char *name = SpriteAtlas_FrameName(atlas, i);
        if (!starts_with(name, prefix))
            continue;
        if (seen == nth)
            return (s32)i;
        ++seen;
    }
    return -1;
}

void SpriteAtlas_DrawFrame(
    GSGLOBAL *gs,
    const SpriteAtlas *atlas,
    u16 frame_index,
    float x,
    float y,
    float scale_x,
    float scale_y,
    int z,
    u64 color)
{
    const AtlasFrame *frame;
    float dx;
    float dy;
    float dw;
    float dh;

    if (gs == NULL || atlas == NULL || !atlas->loaded || frame_index >= atlas->frame_count)
        return;

    frame = &atlas->frames[frame_index];
    if (frame->flags & 1u)
        return; /* Rotated Sparrow frames are not used by base FNF sheets. */

    dx = x - ((float)frame->frame_x * scale_x);
    dy = y - ((float)frame->frame_y * scale_y);
    dw = (float)frame->width * scale_x;
    dh = (float)frame->height * scale_y;

    TextureAsset_Draw(
        gs,
        &atlas->texture,
        dx,
        dy,
        dx + dw,
        dy + dh,
        (float)frame->x,
        (float)frame->y,
        (float)(frame->x + frame->width),
        (float)(frame->y + frame->height),
        z,
        color);
}
