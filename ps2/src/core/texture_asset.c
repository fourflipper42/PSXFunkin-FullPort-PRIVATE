#include "texture_asset.h"

#include <gsCore.h>
#include <gsMisc.h>
#include <gsTexture.h>
#include <malloc.h>
#include <stdio.h>
#include <string.h>

typedef struct FptxHeader {
    char magic[4];
    u16 version;
    u16 format;
    u32 width;
    u32 height;
    u32 pixel_bytes;
    u32 clut_bytes;
    u32 flags;
    u32 reserved;
} __attribute__((packed)) FptxHeader;

#define FPTX_VERSION 1
#define FPTX_FORMAT_T8 8
#define FPTX_CLUT_BYTES (256u * 4u)
#define GS_VRAM_BYTES (4u * 1024u * 1024u)

static GSGLOBAL *streaming_gs;
static u32 streaming_capacity;
static float draw_x_scale = 1.0f;
static float draw_y_scale = 1.0f;
static float draw_x_offset = 0.0f;
static float draw_y_offset = 0.0f;

static boolean read_exact(AssetFile *file, void *dst, size_t size)
{
    return AssetFile_Read(file, dst, size) == size;
}

void TextureAsset_InitStreaming(GSGLOBAL *gs)
{
    if (gs == NULL)
        return;

    streaming_gs = gs;
    streaming_capacity = gs->CurrentPointer < GS_VRAM_BYTES
        ? GS_VRAM_BYTES - gs->CurrentPointer
        : 0;

    /* Direct transfers avoid consuming the one-shot render queue with large
     * atlas uploads. The manager still caches and evicts textures by use. */
    gsKit_TexManager_init(gs);
    gsKit_TexManager_setmode(gs, ETM_DIRECT);

    printf("[PS2] streamed texture VRAM: %u KiB available\n",
        (unsigned)(streaming_capacity / 1024u));
}

void TextureAsset_EndFrame(GSGLOBAL *gs)
{
    if (gs != NULL && gs == streaming_gs)
        gsKit_TexManager_nextFrame(gs);
}

boolean TextureAsset_Load(GSGLOBAL *gs, TextureAsset *asset, const char *path, boolean linear_filter)
{
    AssetFile file;
    FptxHeader header;
    u32 texture_vram_size;
    u32 clut_vram_size;
    u32 required_vram;
    boolean streamed;

    if (gs == NULL || asset == NULL || path == NULL)
        return false;

    memset(asset, 0, sizeof(*asset));
    memset(&file, 0, sizeof(file));
    if (!AssetFile_Open(&file, path))
        return false;

    if (!read_exact(&file, &header, sizeof(header)))
        goto fail;
    if (memcmp(header.magic, "FPTX", 4) != 0 ||
        header.version != FPTX_VERSION ||
        header.format != FPTX_FORMAT_T8 ||
        header.width == 0 || header.height == 0 ||
        header.width > 4096 || header.height > 4096 ||
        header.pixel_bytes != header.width * header.height ||
        header.clut_bytes != FPTX_CLUT_BYTES)
        goto fail;

    asset->texture.Width = header.width;
    asset->texture.Height = header.height;
    asset->texture.PSM = GS_PSM_T8;
    asset->texture.ClutPSM = GS_PSM_CT32;
    asset->texture.ClutStorageMode = GS_CLUT_STORAGE_CSM1;
    asset->texture.Filter = linear_filter ? GS_FILTER_LINEAR : GS_FILTER_NEAREST;
    asset->texture.Vram = 0;
    asset->texture.VramClut = 0;

    texture_vram_size = gsKit_texture_size(
        asset->texture.Width,
        asset->texture.Height,
        asset->texture.PSM);
    clut_vram_size = gsKit_texture_size(16, 16, GS_PSM_CT32);
    required_vram = texture_vram_size + clut_vram_size;
    streamed = gs == streaming_gs && streaming_capacity != 0;

    if (streamed && required_vram > streaming_capacity) {
        printf("[PS2] texture too large for streamed GS cache: %ux%u needs %u KiB, cache %u KiB\n",
            (unsigned)header.width,
            (unsigned)header.height,
            (unsigned)(required_vram / 1024u),
            (unsigned)(streaming_capacity / 1024u));
        goto fail;
    }

    asset->texture.Mem = (u32 *)memalign(128, header.pixel_bytes);
    asset->texture.Clut = (u32 *)memalign(128, header.clut_bytes);
    if (asset->texture.Mem == NULL || asset->texture.Clut == NULL)
        goto fail;

    if (!read_exact(&file, asset->texture.Mem, header.pixel_bytes) ||
        !read_exact(&file, asset->texture.Clut, header.clut_bytes))
        goto fail;
    AssetFile_Close(&file);

    gsKit_setup_tbw(&asset->texture);
    if (streamed) {
        /* Keep indexed pixels + CLUT in EE memory. TexManager_bind() uploads
         * and caches the sheet on first use, then evicts old sheets as needed. */
        asset->texture.Delayed = GS_SETTING_ON;
        asset->loaded = true;
        return true;
    }

    /* Safe fallback for tools/tests that did not initialize the stream cache. */
    asset->texture.Delayed = GS_SETTING_OFF;
    asset->texture.Vram = gsKit_vram_alloc(gs, texture_vram_size, GSKIT_ALLOC_USERBUFFER);
    if (asset->texture.Vram == GSKIT_ALLOC_ERROR)
        goto fail_memory;
    asset->texture.VramClut = gsKit_vram_alloc(gs, clut_vram_size, GSKIT_ALLOC_USERBUFFER);
    if (asset->texture.VramClut == GSKIT_ALLOC_ERROR)
        goto fail_memory;

    gsKit_texture_upload(gs, &asset->texture);
    free(asset->texture.Mem);
    free(asset->texture.Clut);
    asset->texture.Mem = NULL;
    asset->texture.Clut = NULL;
    asset->loaded = true;
    return true;

fail:
    AssetFile_Close(&file);
fail_memory:
    if (asset->texture.Mem != NULL)
        free(asset->texture.Mem);
    if (asset->texture.Clut != NULL)
        free(asset->texture.Clut);
    memset(asset, 0, sizeof(*asset));
    return false;
}

void TextureAsset_Forget(TextureAsset *asset)
{
    if (asset == NULL)
        return;

    if (streaming_gs != NULL && asset->loaded && asset->texture.Delayed)
        gsKit_TexManager_free(streaming_gs, &asset->texture);
    if (asset->texture.Mem != NULL)
        free(asset->texture.Mem);
    if (asset->texture.Clut != NULL)
        free(asset->texture.Clut);
    memset(asset, 0, sizeof(*asset));
}

void TextureAsset_ClearVRAM(GSGLOBAL *gs)
{
    if (gs == NULL)
        return;

    if (gs == streaming_gs) {
        /* Drop the manager's cache map without disturbing gsKit's frame buffers. */
        gsKit_TexManager_init(gs);
    } else {
        gsKit_vram_clear(gs);
    }
}

void TextureAsset_SetDrawTransform(
    float x_scale,
    float y_scale,
    float x_offset,
    float y_offset)
{
    draw_x_scale = x_scale;
    draw_y_scale = y_scale;
    draw_x_offset = x_offset;
    draw_y_offset = y_offset;
}

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
    u64 color)
{
    GSTEXTURE *texture;

    if (gs == NULL || asset == NULL || !asset->loaded)
        return;

    texture = (GSTEXTURE *)&asset->texture;
    if (texture->Delayed)
        gsKit_TexManager_bind(gs, texture);

    gsKit_prim_sprite_texture(
        gs,
        texture,
        draw_x_offset + x1 * draw_x_scale,
        draw_y_offset + y1 * draw_y_scale,
        u1,
        v1,
        draw_x_offset + x2 * draw_x_scale,
        draw_y_offset + y2 * draw_y_scale,
        u2,
        v2,
        z,
        color);
}
