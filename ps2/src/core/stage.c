#include "stage.h"

#include "asset_file.h"
#include "mem.h"
#include "timer.h"
#include <stdio.h>
#include <string.h>

typedef struct StageHeader {
    char magic[4];
    u16 version;
    u16 prop_count;
    u32 string_bytes;
    u32 animation_count;
    u32 indices_count;
    u32 flags;
    float camera_zoom;
    u32 prop_size;
    u32 animation_size;
    u32 character_slot_size;
} __attribute__((packed)) StageHeader;

#define STAGE_VERSION 1
#define STAGE_PROP_FLIP_X       (1u << 0)
#define STAGE_PROP_FLIP_Y       (1u << 1)
#define STAGE_PROP_PIXEL        (1u << 2)
#define STAGE_PROP_ANIMATED     (1u << 3)
#define STAGE_PROP_HAS_COLOR    (1u << 4)

#define STAGE_ANIM_LOOPED       (1u << 0)
#define STAGE_ANIM_FLIP_X       (1u << 1)
#define STAGE_ANIM_FLIP_Y       (1u << 2)
#define STAGE_NO_STRING         0xFFFFFFFFu

static boolean is_disc_base(const char *base)
{
    return base != NULL && (base[0] == '\\' || strncmp(base, "cdrom0:", 7) == 0);
}

static void stage_path(char *out, size_t out_size, const char *base, const char *leaf)
{
    char separator = is_disc_base(base) ? '\\' : '/';
    size_t len = strlen(base);
    if (len != 0 && (base[len - 1] == '/' || base[len - 1] == '\\'))
        snprintf(out, out_size, "%s%s", base, leaf);
    else
        snprintf(out, out_size, "%s%c%s", base, separator, leaf);
}

static const char *stage_string(const Stage *stage, u32 offset)
{
    if (stage == NULL || !stage->loaded || offset == STAGE_NO_STRING || offset >= stage->string_bytes)
        return NULL;
    return stage->strings + offset;
}

static const StageAnimData *prop_anim(const Stage *stage, u16 prop_index, u16 local_index)
{
    const StagePropData *prop;
    u32 index;
    if (stage == NULL || prop_index >= stage->prop_count)
        return NULL;
    prop = &stage->props[prop_index];
    if (local_index >= prop->animation_count)
        return NULL;
    index = prop->animation_start + local_index;
    if (index >= stage->animation_count)
        return NULL;
    return &stage->animations[index];
}

static s32 prop_find_anim(const Stage *stage, u16 prop_index, const char *name)
{
    const StagePropData *prop;
    u16 i;
    if (stage == NULL || name == NULL || prop_index >= stage->prop_count)
        return -1;
    prop = &stage->props[prop_index];
    for (i = 0; i < prop->animation_count; ++i) {
        const StageAnimData *anim = prop_anim(stage, prop_index, i);
        const char *anim_name = anim != NULL ? stage_string(stage, anim->name_offset) : NULL;
        if (anim_name != NULL && strcmp(anim_name, name) == 0)
            return (s32)i;
    }
    return -1;
}

static u16 prop_frame_count(const Stage *stage, u16 prop_index, const StageAnimData *anim)
{
    const StagePropRuntime *runtime;
    const char *prefix;
    if (stage == NULL || anim == NULL || prop_index >= stage->prop_count)
        return 0;
    runtime = &stage->runtime[prop_index];
    if (anim->index_count != 0)
        return anim->index_count;
    prefix = stage_string(stage, anim->prefix_offset);
    return SpriteAtlas_CountPrefix(&runtime->atlas, prefix);
}

static s32 prop_atlas_frame(const Stage *stage, u16 prop_index, const StageAnimData *anim, u16 logical_frame)
{
    const StagePropRuntime *runtime;
    const char *prefix;
    u16 prefix_index;

    if (stage == NULL || anim == NULL || prop_index >= stage->prop_count)
        return -1;
    runtime = &stage->runtime[prop_index];
    prefix = stage_string(stage, anim->prefix_offset);
    if (prefix == NULL)
        return -1;

    if (anim->index_count != 0) {
        u32 index = anim->index_offset + logical_frame;
        if (logical_frame >= anim->index_count || index >= stage->indices_count)
            return -1;
        prefix_index = stage->frame_indices[index];
    } else {
        prefix_index = logical_frame;
    }
    return SpriteAtlas_FindPrefixNth(&runtime->atlas, prefix, prefix_index);
}

static boolean prop_play(Stage *stage, u16 prop_index, const char *name, boolean restart)
{
    StagePropRuntime *runtime;
    s32 index;
    if (stage == NULL || prop_index >= stage->prop_count || name == NULL)
        return false;
    runtime = &stage->runtime[prop_index];
    index = prop_find_anim(stage, prop_index, name);
    if (index < 0)
        return false;
    if (!restart && runtime->current_animation == index)
        return true;
    runtime->current_animation = (s16)index;
    runtime->current_frame = 0;
    runtime->frame_timer = 0;
    runtime->finished = false;
    return true;
}

static void prop_tick(Stage *stage, u16 prop_index)
{
    StagePropRuntime *runtime;
    const StageAnimData *anim;
    u16 count;
    fixed_t duration;

    if (stage == NULL || prop_index >= stage->prop_count)
        return;
    runtime = &stage->runtime[prop_index];
    if (!runtime->loaded || runtime->current_animation < 0)
        return;

    anim = prop_anim(stage, prop_index, (u16)runtime->current_animation);
    if (anim == NULL || anim->frame_rate == 0)
        return;
    count = prop_frame_count(stage, prop_index, anim);
    if (count <= 1)
        return;

    duration = FIXED_DEC(1, anim->frame_rate);
    runtime->frame_timer += timer_dt;
    while (runtime->frame_timer >= duration) {
        runtime->frame_timer -= duration;
        ++runtime->current_frame;
        if (runtime->current_frame >= count) {
            if (anim->flags & STAGE_ANIM_LOOPED) {
                runtime->current_frame = 0;
            } else {
                runtime->current_frame = count - 1;
                runtime->frame_timer = 0;
                runtime->finished = true;
                break;
            }
        }
    }
}

static u64 prop_color(const StagePropData *prop)
{
    u32 packed;
    u8 r, g, b, a;
    float alpha;

    if (prop == NULL)
        return GS_SETREG_RGBAQ(0x80, 0x80, 0x80, 0x80, 0);

    packed = (prop->flags & STAGE_PROP_HAS_COLOR) ? prop->color : 0xFFFFFFFFu;
    r = (u8)(packed & 0xFFu);
    g = (u8)((packed >> 8) & 0xFFu);
    b = (u8)((packed >> 16) & 0xFFu);
    a = (u8)((packed >> 24) & 0xFFu);
    alpha = prop->alpha;
    if (alpha < 0.0f) alpha = 0.0f;
    if (alpha > 1.0f) alpha = 1.0f;
    a = (u8)(((float)a * alpha * 128.0f) / 255.0f);

    /* Textured GS modulation uses 0x80 as neutral RGB and full alpha. */
    r = (u8)(((u32)r * 0x80u + 127u) / 255u);
    g = (u8)(((u32)g * 0x80u + 127u) / 255u);
    b = (u8)(((u32)b * 0x80u + 127u) / 255u);
    return GS_SETREG_RGBAQ(r, g, b, a, 0);
}

static void sort_draw_order(Stage *stage)
{
    u16 i;
    for (i = 0; i < stage->prop_count; ++i)
        stage->draw_order[i] = i;

    for (i = 1; i < stage->prop_count; ++i) {
        u16 key = stage->draw_order[i];
        s32 key_z = stage->props[key].z_index;
        s16 j = (s16)i - 1;
        while (j >= 0 && stage->props[stage->draw_order[j]].z_index > key_z) {
            stage->draw_order[j + 1] = stage->draw_order[j];
            --j;
        }
        stage->draw_order[j + 1] = key;
    }
}

boolean Stage_Load(GSGLOBAL *gs, Stage *stage, const char *base_path)
{
    AssetFile file;
    StageHeader *header;
    u8 *cursor;
    size_t minimum;
    size_t got;
    u16 i;
    char path[256];

    if (gs == NULL || stage == NULL || base_path == NULL)
        return false;

    memset(stage, 0, sizeof(*stage));
    memset(&file, 0, sizeof(file));
    strncpy(stage->base_path, base_path, sizeof(stage->base_path) - 1);
    stage->base_path[sizeof(stage->base_path) - 1] = '\0';

    stage_path(path, sizeof(path), base_path, is_disc_base(base_path) ? "STAGE.FSTG;1" : "STAGE.FSTG");
    if (!AssetFile_Open(&file, path))
        return false;

    stage->config_size = AssetFile_Size(&file);
    if (stage->config_size < sizeof(StageHeader) + sizeof(StageCharacterSlot) * 3u)
        goto fail;
    stage->config_blob = Mem_Alloc(stage->config_size);
    if (stage->config_blob == NULL)
        goto fail;
    got = AssetFile_Read(&file, stage->config_blob, stage->config_size);
    AssetFile_Close(&file);
    if (got != stage->config_size)
        goto fail;

    header = (StageHeader *)stage->config_blob;
    if (memcmp(header->magic, "FSTG", 4) != 0 ||
        header->version != STAGE_VERSION ||
        header->prop_size != sizeof(StagePropData) ||
        header->animation_size != sizeof(StageAnimData) ||
        header->character_slot_size != sizeof(StageCharacterSlot))
        goto fail;

    minimum = sizeof(StageHeader) + sizeof(StageCharacterSlot) * 3u +
        (size_t)header->prop_count * sizeof(StagePropData) +
        (size_t)header->animation_count * sizeof(StageAnimData) +
        (size_t)header->indices_count * sizeof(u16) +
        header->string_bytes;
    if (minimum > stage->config_size)
        goto fail;

    cursor = (u8 *)stage->config_blob + sizeof(StageHeader);
    memcpy(&stage->bf, cursor, sizeof(StageCharacterSlot));
    cursor += sizeof(StageCharacterSlot);
    memcpy(&stage->dad, cursor, sizeof(StageCharacterSlot));
    cursor += sizeof(StageCharacterSlot);
    memcpy(&stage->gf, cursor, sizeof(StageCharacterSlot));
    cursor += sizeof(StageCharacterSlot);

    stage->props = (StagePropData *)cursor;
    cursor += (size_t)header->prop_count * sizeof(StagePropData);
    stage->animations = (StageAnimData *)cursor;
    cursor += (size_t)header->animation_count * sizeof(StageAnimData);
    stage->frame_indices = (u16 *)cursor;
    cursor += (size_t)header->indices_count * sizeof(u16);
    stage->strings = (char *)cursor;

    stage->prop_count = header->prop_count;
    stage->animation_count = header->animation_count;
    stage->indices_count = header->indices_count;
    stage->string_bytes = header->string_bytes;
    stage->camera_zoom = header->camera_zoom;

    if (stage->prop_count != 0) {
        stage->runtime = (StagePropRuntime *)Mem_Alloc(sizeof(StagePropRuntime) * stage->prop_count);
        stage->draw_order = (u16 *)Mem_Alloc(sizeof(u16) * stage->prop_count);
        if (stage->runtime == NULL || stage->draw_order == NULL)
            goto fail;
        memset(stage->runtime, 0, sizeof(StagePropRuntime) * stage->prop_count);
        sort_draw_order(stage);
    }

    stage->loaded = true;
    for (i = 0; i < stage->prop_count; ++i) {
        StagePropRuntime *runtime = &stage->runtime[i];
        const StagePropData *prop = &stage->props[i];
        char leaf[32];

        runtime->current_animation = -1;
        snprintf(leaf, sizeof(leaf), "P%03u.FPTX%s", (unsigned)i, is_disc_base(base_path) ? ";1" : "");
        stage_path(path, sizeof(path), base_path, leaf);

        if (prop->flags & STAGE_PROP_ANIMATED) {
            char atlas_path[256];
            char frames_leaf[32];
            snprintf(frames_leaf, sizeof(frames_leaf), "P%03u.FATL%s", (unsigned)i, is_disc_base(base_path) ? ";1" : "");
            stage_path(atlas_path, sizeof(atlas_path), base_path, frames_leaf);
            runtime->loaded = SpriteAtlas_Load(gs, &runtime->atlas, path, atlas_path,
                (prop->flags & STAGE_PROP_PIXEL) == 0);
            if (runtime->loaded && prop->animation_count != 0) {
                const char *start = stage_string(stage, prop->starting_name_offset);
                if (start == NULL || !prop_play(stage, i, start, true))
                    prop_play(stage, i, stage_string(stage, prop_anim(stage, i, 0)->name_offset), true);
            }
        } else {
            runtime->loaded = TextureAsset_Load(gs, &runtime->texture, path,
                (prop->flags & STAGE_PROP_PIXEL) == 0);
        }

        if (!runtime->loaded) {
            printf("[PS2] stage prop %u failed to load\n", (unsigned)i);
            goto fail;
        }
    }

    return true;

fail:
    AssetFile_Close(&file);
    Stage_Forget(stage);
    return false;
}

void Stage_Forget(Stage *stage)
{
    u16 i;
    if (stage == NULL)
        return;
    if (stage->runtime != NULL) {
        for (i = 0; i < stage->prop_count; ++i) {
            if (stage->props != NULL && (stage->props[i].flags & STAGE_PROP_ANIMATED))
                SpriteAtlas_Forget(&stage->runtime[i].atlas);
            else
                TextureAsset_Forget(&stage->runtime[i].texture);
        }
        Mem_Free(stage->runtime);
    }
    if (stage->draw_order != NULL)
        Mem_Free(stage->draw_order);
    if (stage->config_blob != NULL)
        Mem_Free(stage->config_blob);
    memset(stage, 0, sizeof(*stage));
}

void Stage_Tick(Stage *stage)
{
    u16 i;
    if (stage == NULL || !stage->loaded)
        return;
    for (i = 0; i < stage->prop_count; ++i) {
        if (stage->props[i].flags & STAGE_PROP_ANIMATED)
            prop_tick(stage, i);
    }
}

void Stage_Beat(Stage *stage, s32 beat)
{
    u16 i;
    if (stage == NULL || !stage->loaded)
        return;

    for (i = 0; i < stage->prop_count; ++i) {
        StagePropRuntime *runtime = &stage->runtime[i];
        const StagePropData *prop = &stage->props[i];
        s32 cadence;
        const char *name;

        if (!(prop->flags & STAGE_PROP_ANIMATED) || prop->animation_count == 0 || !runtime->loaded)
            continue;
        cadence = (s32)(prop->dance_every + 0.5f);
        if (cadence < 1) cadence = 1;
        if ((beat % cadence) != 0)
            continue;

        if (prop_find_anim(stage, i, "danceLeft") >= 0 && prop_find_anim(stage, i, "danceRight") >= 0) {
            name = runtime->dance_right ? "danceRight" : "danceLeft";
            runtime->dance_right = !runtime->dance_right;
            prop_play(stage, i, name, true);
        } else {
            name = stage_string(stage, prop->starting_name_offset);
            if (name != NULL)
                prop_play(stage, i, name, true);
        }
    }
}

static void draw_prop(GSGLOBAL *gs, const Stage *stage, const StageCamera *camera, u16 prop_index)
{
    const StagePropData *prop;
    const StagePropRuntime *runtime;
    float zoom;
    float world_scale;
    float x;
    float y;
    float sx;
    float sy;
    boolean flip_x;
    boolean flip_y;
    u64 color;

    if (stage == NULL || prop_index >= stage->prop_count)
        return;
    prop = &stage->props[prop_index];
    runtime = &stage->runtime[prop_index];
    if (!runtime->loaded)
        return;

    zoom = camera != NULL ? camera->zoom : stage->camera_zoom;
    if (zoom <= 0.0f) zoom = 1.0f;
    world_scale = 0.5f * zoom;
    x = (prop->x - ((camera != NULL ? camera->scroll_x : 0.0f) * prop->scroll_x)) * world_scale;
    y = (prop->y - ((camera != NULL ? camera->scroll_y : 0.0f) * prop->scroll_y)) * world_scale;
    sx = prop->scale_x * world_scale;
    sy = prop->scale_y * world_scale;
    flip_x = (prop->flags & STAGE_PROP_FLIP_X) != 0;
    flip_y = (prop->flags & STAGE_PROP_FLIP_Y) != 0;
    color = prop_color(prop);

    if (prop->flags & STAGE_PROP_ANIMATED) {
        const StageAnimData *anim;
        s32 frame_index;
        if (runtime->current_animation < 0)
            return;
        anim = prop_anim(stage, prop_index, (u16)runtime->current_animation);
        if (anim == NULL)
            return;
        frame_index = prop_atlas_frame(stage, prop_index, anim, runtime->current_frame);
        if (frame_index < 0)
            return;
        x -= anim->offset_x * sx;
        y -= anim->offset_y * sy;
        flip_x = flip_x ^ ((anim->flags & STAGE_ANIM_FLIP_X) != 0);
        flip_y = flip_y ^ ((anim->flags & STAGE_ANIM_FLIP_Y) != 0);
        SpriteAtlas_DrawFrameEx(
            gs, &runtime->atlas, (u16)frame_index,
            x, y, sx, sy, flip_x, flip_y,
            2, color);
    } else {
        float w = (float)runtime->texture.texture.Width * sx;
        float h = (float)runtime->texture.texture.Height * sy;
        float u1 = flip_x ? (float)runtime->texture.texture.Width : 0.0f;
        float u2 = flip_x ? 0.0f : (float)runtime->texture.texture.Width;
        float v1 = flip_y ? (float)runtime->texture.texture.Height : 0.0f;
        float v2 = flip_y ? 0.0f : (float)runtime->texture.texture.Height;
        TextureAsset_Draw(
            gs, &runtime->texture,
            x, y, x + w, y + h,
            u1, v1, u2, v2,
            2, color);
    }
}

void Stage_DrawRange(
    GSGLOBAL *gs,
    const Stage *stage,
    const StageCamera *camera,
    s32 z_min,
    s32 z_max)
{
    u16 order;
    if (gs == NULL || stage == NULL || !stage->loaded)
        return;
    for (order = 0; order < stage->prop_count; ++order) {
        u16 index = stage->draw_order[order];
        s32 z = stage->props[index].z_index;
        if (z < z_min)
            continue;
        if (z >= z_max)
            break;
        draw_prop(gs, stage, camera, index);
    }
}

const StageCharacterSlot *Stage_PlayerSlot(const Stage *stage)
{
    return stage != NULL && stage->loaded ? &stage->bf : NULL;
}

const StageCharacterSlot *Stage_OpponentSlot(const Stage *stage)
{
    return stage != NULL && stage->loaded ? &stage->dad : NULL;
}

const StageCharacterSlot *Stage_GirlfriendSlot(const Stage *stage)
{
    return stage != NULL && stage->loaded ? &stage->gf : NULL;
}

float Stage_CameraZoom(const Stage *stage)
{
    return stage != NULL && stage->loaded ? stage->camera_zoom : 1.0f;
}
