#include "sprite_atlas.h"

#include "asset_file.h"
#include "mem.h"
#include <stdio.h>
#include <string.h>

typedef struct AtlasHeaderV1 {
    char magic[4];
    u16 version;
    u16 frame_count;
    u32 string_bytes;
    u32 record_size;
} __attribute__((packed)) AtlasHeaderV1;

typedef struct AtlasHeaderV2 {
    char magic[4];
    u16 version;
    u16 frame_count;
    u32 string_bytes;
    u32 record_size;
    u16 page_count;
    u16 reserved;
} __attribute__((packed)) AtlasHeaderV2;

#define ATLAS_VERSION_V1 1
#define ATLAS_VERSION_V2 2
#define ATLAS_DEFAULT_RESIDENT_PAGES 2

static boolean starts_with(const char *text, const char *prefix)
{
    size_t n;
    if (text == NULL || prefix == NULL)
        return false;
    n = strlen(prefix);
    return strncmp(text, prefix, n) == 0;
}

static boolean atlas_page_path(
    char *out,
    size_t out_size,
    const char *page0_path,
    u16 page_index)
{
    const char *ext;
    size_t prefix_len;
    int written;

    if (out == NULL || out_size == 0 || page0_path == NULL)
        return false;
    if (page_index == 0) {
        written = snprintf(out, out_size, "%s", page0_path);
        return written >= 0 && (size_t)written < out_size;
    }

    ext = strstr(page0_path, ".FPTX");
    if (ext == NULL)
        ext = strstr(page0_path, ".fptx");
    if (ext == NULL)
        return false;

    prefix_len = (size_t)(ext - page0_path);
    written = snprintf(
        out,
        out_size,
        "%.*s_P%03u%s",
        (int)prefix_len,
        page0_path,
        (unsigned)page_index,
        ext);
    return written >= 0 && (size_t)written < out_size;
}

static void atlas_reset_usage_if_wrapped(SpriteAtlas *atlas)
{
    u16 i;
    if (atlas->draw_serial != 0)
        return;
    atlas->draw_serial = 1;
    for (i = 0; i < atlas->texture_count; ++i) {
        if (atlas->textures[i].loaded)
            atlas->page_last_used[i] = 1;
        else
            atlas->page_last_used[i] = 0;
    }
}

static TextureAsset *atlas_page_for_draw(
    GSGLOBAL *gs,
    const SpriteAtlas *atlas_const,
    u16 page_index)
{
    SpriteAtlas *atlas = (SpriteAtlas *)atlas_const;
    u16 i;

    if (gs == NULL || atlas == NULL || !atlas->loaded ||
        page_index >= atlas->texture_count)
        return NULL;
    if (atlas->page_failed[page_index])
        return NULL;

    ++atlas->draw_serial;
    atlas_reset_usage_if_wrapped(atlas);

    if (atlas->textures[page_index].loaded) {
        atlas->page_last_used[page_index] = atlas->draw_serial;
        return &atlas->textures[page_index];
    }

    while (atlas->resident_pages >= atlas->resident_limit) {
        u16 victim = atlas->texture_count;
        u32 oldest = 0xffffffffu;

        for (i = 0; i < atlas->texture_count; ++i) {
            if (i == page_index || !atlas->textures[i].loaded)
                continue;
            if (atlas->page_last_used[i] <= oldest) {
                oldest = atlas->page_last_used[i];
                victim = i;
            }
        }

        if (victim >= atlas->texture_count)
            break;

        TextureAsset_Forget(&atlas->textures[victim]);
        atlas->page_last_used[victim] = 0;
        if (atlas->resident_pages > 0)
            --atlas->resident_pages;
    }

    {
        char page_path[320];
        if (!atlas_page_path(page_path, sizeof(page_path), atlas->texture_path, page_index) ||
            !TextureAsset_Load(
                gs,
                &atlas->textures[page_index],
                page_path,
                atlas->linear_filter)) {
            atlas->page_failed[page_index] = 1;
            printf("[PS2] atlas page %u failed: %s\n",
                (unsigned)page_index,
                atlas->texture_path);
            return NULL;
        }
    }

    ++atlas->resident_pages;
    atlas->page_last_used[page_index] = atlas->draw_serial;
    return &atlas->textures[page_index];
}

boolean SpriteAtlas_Load(
    GSGLOBAL *gs,
    SpriteAtlas *atlas,
    const char *texture_path,
    const char *frames_path,
    boolean linear_filter)
{
    AssetFile file;
    AtlasHeaderV1 *base_header;
    size_t header_size;
    size_t minimum;
    size_t got;
    u16 frame_count;
    u16 page_count;
    u32 string_bytes;
    u32 record_size;
    u16 i;
    int written;

    (void)gs;

    if (atlas == NULL || texture_path == NULL || frames_path == NULL)
        return false;

    memset(atlas, 0, sizeof(*atlas));
    memset(&file, 0, sizeof(file));

    /* Metadata is tiny and stays resident. Texture page pixels are intentionally
     * not loaded here: each atlas keeps only a tiny LRU page window in EE RAM. */
    if (!AssetFile_Open(&file, frames_path))
        goto fail;
    atlas->frame_blob_size = AssetFile_Size(&file);
    if (atlas->frame_blob_size < sizeof(AtlasHeaderV1))
        goto fail;

    atlas->frame_blob = Mem_Alloc(atlas->frame_blob_size);
    if (atlas->frame_blob == NULL)
        goto fail;
    got = AssetFile_Read(&file, atlas->frame_blob, atlas->frame_blob_size);
    AssetFile_Close(&file);
    if (got != atlas->frame_blob_size)
        goto fail;

    base_header = (AtlasHeaderV1 *)atlas->frame_blob;
    if (memcmp(base_header->magic, "FATL", 4) != 0)
        goto fail;

    if (base_header->version == ATLAS_VERSION_V1) {
        header_size = sizeof(AtlasHeaderV1);
        frame_count = base_header->frame_count;
        string_bytes = base_header->string_bytes;
        record_size = base_header->record_size;
        page_count = 1;
    } else if (base_header->version == ATLAS_VERSION_V2) {
        AtlasHeaderV2 *header;
        if (atlas->frame_blob_size < sizeof(AtlasHeaderV2))
            goto fail;
        header = (AtlasHeaderV2 *)atlas->frame_blob;
        header_size = sizeof(AtlasHeaderV2);
        frame_count = header->frame_count;
        string_bytes = header->string_bytes;
        record_size = header->record_size;
        page_count = header->page_count;
    } else {
        goto fail;
    }

    if (frame_count == 0 || page_count == 0 || record_size != sizeof(AtlasFrame))
        goto fail;

    minimum = header_size +
        ((size_t)frame_count * sizeof(AtlasFrame)) +
        string_bytes;
    if (minimum > atlas->frame_blob_size)
        goto fail;

    atlas->frames = (AtlasFrame *)((u8 *)atlas->frame_blob + header_size);
    atlas->strings = (char *)(atlas->frames + frame_count);
    atlas->string_bytes = string_bytes;
    atlas->frame_count = frame_count;
    atlas->texture_count = page_count;
    atlas->linear_filter = linear_filter;
    atlas->resident_limit = page_count < ATLAS_DEFAULT_RESIDENT_PAGES
        ? page_count
        : ATLAS_DEFAULT_RESIDENT_PAGES;

    written = snprintf(atlas->texture_path, sizeof(atlas->texture_path), "%s", texture_path);
    if (written < 0 || (size_t)written >= sizeof(atlas->texture_path))
        goto fail;

    for (i = 0; i < frame_count; ++i) {
        if (base_header->version == ATLAS_VERSION_V1)
            atlas->frames[i].page_index = 0;
        if (atlas->frames[i].page_index >= page_count)
            goto fail;
        if (atlas->frames[i].name_offset >= string_bytes)
            goto fail;
    }

    atlas->textures = (TextureAsset *)Mem_Alloc(sizeof(TextureAsset) * page_count);
    atlas->page_last_used = (u32 *)Mem_Alloc(sizeof(u32) * page_count);
    atlas->page_failed = (u8 *)Mem_Alloc(sizeof(u8) * page_count);
    if (atlas->textures == NULL || atlas->page_last_used == NULL || atlas->page_failed == NULL)
        goto fail;
    memset(atlas->textures, 0, sizeof(TextureAsset) * page_count);
    memset(atlas->page_last_used, 0, sizeof(u32) * page_count);
    memset(atlas->page_failed, 0, sizeof(u8) * page_count);

    atlas->loaded = true;
    return true;

fail:
    AssetFile_Close(&file);
    if (atlas->textures != NULL) {
        for (i = 0; i < atlas->texture_count; ++i)
            TextureAsset_Forget(&atlas->textures[i]);
        Mem_Free(atlas->textures);
    }
    if (atlas->page_last_used != NULL)
        Mem_Free(atlas->page_last_used);
    if (atlas->page_failed != NULL)
        Mem_Free(atlas->page_failed);
    if (atlas->frame_blob != NULL)
        Mem_Free(atlas->frame_blob);
    memset(atlas, 0, sizeof(*atlas));
    return false;
}

void SpriteAtlas_Forget(SpriteAtlas *atlas)
{
    u16 i;
    if (atlas == NULL)
        return;
    if (atlas->textures != NULL) {
        for (i = 0; i < atlas->texture_count; ++i)
            TextureAsset_Forget(&atlas->textures[i]);
        Mem_Free(atlas->textures);
    }
    if (atlas->page_last_used != NULL)
        Mem_Free(atlas->page_last_used);
    if (atlas->page_failed != NULL)
        Mem_Free(atlas->page_failed);
    if (atlas->frame_blob != NULL)
        Mem_Free(atlas->frame_blob);
    memset(atlas, 0, sizeof(*atlas));
}

const char *SpriteAtlas_FrameName(const SpriteAtlas *atlas, u16 frame_index)
{
    u32 offset;
    const char *value;
    size_t remaining;

    if (atlas == NULL || !atlas->loaded || frame_index >= atlas->frame_count)
        return NULL;
    offset = atlas->frames[frame_index].name_offset;
    if (offset >= atlas->string_bytes)
        return NULL;
    value = atlas->strings + offset;
    remaining = atlas->string_bytes - offset;
    if (memchr(value, '\0', remaining) == NULL)
        return NULL;
    return value;
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
    u64 color)
{
    const AtlasFrame *frame;
    TextureAsset *texture;
    float trim_x;
    float trim_y;
    float dx;
    float dy;
    float dw;
    float dh;
    float u1;
    float u2;
    float v1;
    float v2;

    if (gs == NULL || atlas == NULL || !atlas->loaded || frame_index >= atlas->frame_count)
        return;

    frame = &atlas->frames[frame_index];
    if (frame->page_index >= atlas->texture_count)
        return;
    if (frame->flags & 1u)
        return; /* Rotated Sparrow frames are not used by base FNF sheets. */

    texture = atlas_page_for_draw(gs, atlas, frame->page_index);
    if (texture == NULL)
        return;

    trim_x = -(float)frame->frame_x;
    trim_y = -(float)frame->frame_y;
    if (flip_x)
        trim_x = (float)frame->frame_width - trim_x - (float)frame->width;
    if (flip_y)
        trim_y = (float)frame->frame_height - trim_y - (float)frame->height;

    dx = x + trim_x * scale_x;
    dy = y + trim_y * scale_y;
    dw = (float)frame->width * scale_x;
    dh = (float)frame->height * scale_y;

    u1 = (float)frame->x;
    u2 = (float)(frame->x + frame->width);
    v1 = (float)frame->y;
    v2 = (float)(frame->y + frame->height);
    if (flip_x) {
        float tmp = u1;
        u1 = u2;
        u2 = tmp;
    }
    if (flip_y) {
        float tmp = v1;
        v1 = v2;
        v2 = tmp;
    }

    TextureAsset_Draw(
        gs,
        texture,
        dx,
        dy,
        dx + dw,
        dy + dh,
        u1,
        v1,
        u2,
        v2,
        z,
        color);
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
    SpriteAtlas_DrawFrameEx(
        gs,
        atlas,
        frame_index,
        x,
        y,
        scale_x,
        scale_y,
        false,
        false,
        z,
        color);
}
