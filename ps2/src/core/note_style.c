#include "note_style.h"

#include "asset_file.h"
#include "mem.h"
#include <stdio.h>
#include <string.h>

typedef struct NoteStyleHeader {
    char magic[4];
    u16 version;
    u16 flags;
    float note_scale;
    float strum_scale;
    float hold_scale;
    float strum_offset_x;
    float strum_offset_y;
    float hold_offset_x;
    float hold_offset_y;
    u32 string_bytes;
    u32 prefixes[20];
} __attribute__((packed)) NoteStyleHeader;

#define NOTE_STYLE_VERSION 1
#define NOTE_STYLE_PIXEL_NOTE  (1u << 0)
#define NOTE_STYLE_PIXEL_STRUM (1u << 1)
#define NOTE_STYLE_PIXEL_HOLD  (1u << 2)

static boolean style_path(
    char *out,
    size_t out_size,
    const char *base,
    const char *filename)
{
    boolean host;
    char separator;
    const char *version;
    int written;

    if (out == NULL || out_size == 0 || base == NULL || filename == NULL)
        return false;

    host = strncmp(base, "host:", 5) == 0 || strchr(base, '/') != NULL;
    separator = host ? '/' : '\\';
    version = host ? "" : ";1";
    written = snprintf(out, out_size, "%s%c%s%s", base, separator, filename, version);
    return written >= 0 && (size_t)written < out_size;
}

static const char *style_string(const NoteStyle *style, u32 offset)
{
    const char *value;
    size_t remaining;

    if (style == NULL || style->strings == NULL || offset >= style->string_bytes)
        return NULL;
    value = style->strings + offset;
    remaining = style->string_bytes - offset;
    if (memchr(value, '\0', remaining) == NULL)
        return NULL;
    return value;
}

static s32 frame_for_prefix(
    const SpriteAtlas *atlas,
    const char *prefix,
    u32 animation_tick)
{
    u16 count;

    if (atlas == NULL || prefix == NULL)
        return -1;
    count = SpriteAtlas_CountPrefix(atlas, prefix);
    if (count == 0)
        return -1;
    return SpriteAtlas_FindPrefixNth(
        atlas,
        prefix,
        (u16)((animation_tick / 2u) % count));
}

static void draw_centered_frame(
    GSGLOBAL *gs,
    const SpriteAtlas *atlas,
    u16 frame_index,
    float center_x,
    float center_y,
    float scale,
    int z,
    u64 color)
{
    const AtlasFrame *frame;
    float x;
    float y;

    if (atlas == NULL || frame_index >= atlas->frame_count)
        return;
    frame = &atlas->frames[frame_index];
    x = center_x - ((float)frame->frame_width * scale * 0.5f);
    y = center_y - ((float)frame->frame_height * scale * 0.5f);
    SpriteAtlas_DrawFrame(gs, atlas, frame_index, x, y, scale, scale, z, color);
}

boolean NoteStyle_Load(GSGLOBAL *gs, NoteStyle *style, const char *base_path)
{
    AssetFile file;
    NoteStyleHeader *header;
    char config_path[320];
    char note_texture[320];
    char note_frames[320];
    char strum_texture[320];
    char strum_frames[320];
    char hold_texture[320];
    size_t got;
    size_t minimum;
    int group;
    int lane;

    if (gs == NULL || style == NULL || base_path == NULL)
        return false;

    memset(style, 0, sizeof(*style));
    memset(&file, 0, sizeof(file));
    if (!style_path(config_path, sizeof(config_path), base_path, "STYLE.FNST") ||
        !style_path(note_texture, sizeof(note_texture), base_path, "NOTE.FPTX") ||
        !style_path(note_frames, sizeof(note_frames), base_path, "NOTE.FATL") ||
        !style_path(strum_texture, sizeof(strum_texture), base_path, "STRUM.FPTX") ||
        !style_path(strum_frames, sizeof(strum_frames), base_path, "STRUM.FATL") ||
        !style_path(hold_texture, sizeof(hold_texture), base_path, "HOLD.FPTX"))
        return false;

    if (!AssetFile_Open(&file, config_path))
        return false;
    style->blob_size = AssetFile_Size(&file);
    if (style->blob_size < sizeof(NoteStyleHeader))
        goto fail;
    style->blob = Mem_Alloc(style->blob_size);
    if (style->blob == NULL)
        goto fail;
    got = AssetFile_Read(&file, style->blob, style->blob_size);
    AssetFile_Close(&file);
    if (got != style->blob_size)
        goto fail;

    header = (NoteStyleHeader *)style->blob;
    if (memcmp(header->magic, "FNST", 4) != 0 || header->version != NOTE_STYLE_VERSION)
        goto fail;
    minimum = sizeof(NoteStyleHeader) + (size_t)header->string_bytes;
    if (minimum > style->blob_size)
        goto fail;

    style->strings = (char *)style->blob + sizeof(NoteStyleHeader);
    style->string_bytes = header->string_bytes;
    style->flags = header->flags;
    style->note_scale = header->note_scale;
    style->strum_scale = header->strum_scale;
    style->hold_scale = header->hold_scale;
    style->strum_offset_x = header->strum_offset_x;
    style->strum_offset_y = header->strum_offset_y;
    style->hold_offset_x = header->hold_offset_x;
    style->hold_offset_y = header->hold_offset_y;

    for (group = 0; group < 5; ++group) {
        for (lane = 0; lane < 4; ++lane) {
            const char *value = style_string(style, header->prefixes[group * 4 + lane]);
            if (value == NULL)
                goto fail;
            switch (group) {
                case 0: style->note_prefix[lane] = value; break;
                case 1: style->strum_static_prefix[lane] = value; break;
                case 2: style->strum_press_prefix[lane] = value; break;
                case 3: style->strum_confirm_prefix[lane] = value; break;
                default: style->strum_confirm_hold_prefix[lane] = value; break;
            }
        }
    }

    if (!SpriteAtlas_Load(
            gs, &style->note_atlas, note_texture, note_frames,
            (style->flags & NOTE_STYLE_PIXEL_NOTE) == 0) ||
        !SpriteAtlas_Load(
            gs, &style->strum_atlas, strum_texture, strum_frames,
            (style->flags & NOTE_STYLE_PIXEL_STRUM) == 0) ||
        !TextureAsset_Load(
            gs, &style->hold_texture, hold_texture,
            (style->flags & NOTE_STYLE_PIXEL_HOLD) == 0))
        goto fail;

    if (style->hold_texture.texture.Width == 0 ||
        (style->hold_texture.texture.Width & 7u) != 0)
        goto fail;

    style->loaded = true;
    printf("[PS2] note style loaded: note=%u frames strum=%u frames hold=%ux%u\n",
        (unsigned)style->note_atlas.frame_count,
        (unsigned)style->strum_atlas.frame_count,
        (unsigned)style->hold_texture.texture.Width,
        (unsigned)style->hold_texture.texture.Height);
    return true;

fail:
    AssetFile_Close(&file);
    NoteStyle_Free(style);
    return false;
}

void NoteStyle_Free(NoteStyle *style)
{
    if (style == NULL)
        return;
    SpriteAtlas_Forget(&style->note_atlas);
    SpriteAtlas_Forget(&style->strum_atlas);
    TextureAsset_Forget(&style->hold_texture);
    if (style->blob != NULL)
        Mem_Free(style->blob);
    memset(style, 0, sizeof(*style));
}

void NoteStyle_DrawTap(
    GSGLOBAL *gs,
    const NoteStyle *style,
    u8 lane,
    float center_x,
    float center_y,
    int z,
    u64 color)
{
    s32 frame;

    if (style == NULL || !style->loaded || lane > 3)
        return;
    frame = frame_for_prefix(&style->note_atlas, style->note_prefix[lane], 0);
    if (frame < 0)
        return;
    draw_centered_frame(
        gs, &style->note_atlas, (u16)frame,
        center_x, center_y, style->note_scale, z, color);
}

void NoteStyle_DrawReceptor(
    GSGLOBAL *gs,
    const NoteStyle *style,
    u8 lane,
    ReceptorVisualState state,
    u32 animation_tick,
    float center_x,
    float center_y,
    int z,
    u64 color)
{
    const char *prefix;
    s32 frame;

    if (style == NULL || !style->loaded || lane > 3)
        return;

    switch (state) {
        case RECEPTOR_PRESS:
            prefix = style->strum_press_prefix[lane];
            break;
        case RECEPTOR_CONFIRM:
            prefix = style->strum_confirm_prefix[lane];
            break;
        case RECEPTOR_CONFIRM_HOLD:
            prefix = style->strum_confirm_hold_prefix[lane];
            break;
        default:
            prefix = style->strum_static_prefix[lane];
            break;
    }

    frame = frame_for_prefix(&style->strum_atlas, prefix, animation_tick);
    if (frame < 0)
        frame = frame_for_prefix(&style->strum_atlas, style->strum_static_prefix[lane], 0);
    if (frame < 0)
        return;

    draw_centered_frame(
        gs, &style->strum_atlas, (u16)frame,
        center_x - style->strum_offset_x,
        center_y - style->strum_offset_y,
        style->strum_scale, z, color);
}

void NoteStyle_DrawHoldPiece(
    GSGLOBAL *gs,
    const NoteStyle *style,
    u8 lane,
    float center_x,
    float top_y,
    float height,
    boolean end_cap,
    int z,
    u64 color)
{
    float slice_width;
    float display_width;
    float u1;
    float u2;
    float v2;

    if (style == NULL || !style->loaded || lane > 3 || height <= 0.0f)
        return;

    slice_width = (float)style->hold_texture.texture.Width / 8.0f;
    display_width = slice_width * style->hold_scale;
    u1 = slice_width * (float)(lane * 2 + (end_cap ? 1 : 0));
    u2 = u1 + slice_width;
    v2 = (float)style->hold_texture.texture.Height;
    if (end_cap && (style->flags & NOTE_STYLE_PIXEL_HOLD) == 0)
        v2 *= 0.9f;

    TextureAsset_Draw(
        gs,
        &style->hold_texture,
        center_x - display_width * 0.5f - style->hold_offset_x,
        top_y - style->hold_offset_y,
        center_x + display_width * 0.5f - style->hold_offset_x,
        top_y + height - style->hold_offset_y,
        u1, 0.0f, u2, v2,
        z,
        color);
}
