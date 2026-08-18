#include "health_icon.h"

#include "asset_file.h"
#include "song_descriptor.h"
#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

typedef struct HealthIconMapHeader {
    char magic[4];
    u16 version;
    u16 flags;
    u32 string_bytes;
    u32 id_offset;
    float scale;
    float offset_x;
    float offset_y;
} __attribute__((packed)) HealthIconMapHeader;

#define HEALTH_MAP_VERSION 1
#define HEALTH_MAP_PIXEL      (1u << 0)
#define HEALTH_MAP_FLIP_X     (1u << 1)
#define HEALTH_MAP_SHOULD_BOP (1u << 2)
#define HEALTH_ICON_IDLE 0
#define HEALTH_ICON_LOSING 1
#define HEALTH_ICON_WINNING 2
#define HEALTH_ICON_LOGICAL_SIZE 75.0f

static void upper_path(char *path)
{
    if (path == NULL)
        return;
    while (*path != '\0') {
        *path = (char)toupper((unsigned char)*path);
        ++path;
    }
}

static boolean disc_base(const char *base)
{
    return base != NULL && (base[0] == '\\' || strncmp(base, "cdrom0:", 7) == 0);
}

static boolean load_map(HealthIcon *icon, const char *character_base)
{
    AssetFile file;
    HealthIconMapHeader header;
    char path[320];
    char strings[128];
    size_t got;
    const char *id;

    if (icon == NULL || character_base == NULL)
        return false;
    memset(&file, 0, sizeof(file));
    if (disc_base(character_base)) {
        SongDescriptor_CharacterFile(path, sizeof(path), character_base, "HEALTH.FHCM");
    } else {
        snprintf(path, sizeof(path), "%s/HEALTH.FHCM", character_base);
    }
    if (!AssetFile_Open(&file, path))
        return false;
    if (AssetFile_Size(&file) < sizeof(header))
        goto fail;
    got = AssetFile_Read(&file, &header, sizeof(header));
    if (got != sizeof(header) || memcmp(header.magic, "FHCM", 4) != 0 ||
        header.version != HEALTH_MAP_VERSION || header.string_bytes == 0 ||
        header.string_bytes > sizeof(strings) || header.id_offset >= header.string_bytes)
        goto fail;
    got = AssetFile_Read(&file, strings, header.string_bytes);
    AssetFile_Close(&file);
    if (got != header.string_bytes || memchr(strings + header.id_offset, '\0',
        header.string_bytes - header.id_offset) == NULL)
        return false;

    id = strings + header.id_offset;
    if (strlen(id) >= sizeof(icon->id))
        return false;
    strcpy(icon->id, id);
    icon->flags = header.flags;
    icon->scale = header.scale <= 0.0f ? 1.0f : header.scale;
    icon->offset_x = header.offset_x * 0.5f;
    icon->offset_y = header.offset_y * 0.5f;
    icon->bounce_scale = 1.0f;
    icon->bounce_target = 1.0f;
    return true;

fail:
    AssetFile_Close(&file);
    return false;
}

static void icon_paths(
    const char *id,
    char *texture,
    size_t texture_size,
    char *frames,
    size_t frames_size)
{
    snprintf(texture, texture_size, "\\GAME\\ICON\\%s\\ICON.FPTX;1", id);
    snprintf(frames, frames_size, "\\GAME\\ICON\\%s\\ICON.FATL;1", id);
    upper_path(texture);
    upper_path(frames);
}

boolean HealthIcon_Load(
    GSGLOBAL *gs,
    HealthIcon *icon,
    const char *character_base)
{
    char texture_path[320];
    char frames_path[320];

    if (gs == NULL || icon == NULL || character_base == NULL)
        return false;
    memset(icon, 0, sizeof(*icon));
    if (!load_map(icon, character_base))
        return false;

    icon_paths(icon->id, texture_path, sizeof(texture_path), frames_path, sizeof(frames_path));
    if (SpriteAtlas_Load(gs, &icon->atlas, texture_path, frames_path,
        (icon->flags & HEALTH_MAP_PIXEL) == 0)) {
        icon->modern = true;
        icon->loaded = true;
        return true;
    }

    if (!TextureAsset_Load(gs, &icon->texture, texture_path,
        (icon->flags & HEALTH_MAP_PIXEL) == 0)) {
        memset(icon, 0, sizeof(*icon));
        return false;
    }
    icon->modern = false;
    icon->loaded = true;
    return true;
}

void HealthIcon_Forget(HealthIcon *icon)
{
    if (icon == NULL)
        return;
    if (icon->modern)
        SpriteAtlas_Forget(&icon->atlas);
    else if (icon->loaded)
        TextureAsset_Forget(&icon->texture);
    memset(icon, 0, sizeof(*icon));
}

static u8 desired_state(s16 health, boolean player)
{
    s32 effective = player ? health : 20000 - health;
    if (effective < 4000)
        return HEALTH_ICON_LOSING;
    if (effective > 16000)
        return HEALTH_ICON_WINNING;
    return HEALTH_ICON_IDLE;
}

static const char *state_prefix(u8 state)
{
    switch (state) {
        case HEALTH_ICON_LOSING: return "losing";
        case HEALTH_ICON_WINNING: return "winning";
        default: return "idle";
    }
}

static u16 modern_frame_count(const HealthIcon *icon)
{
    u16 count;
    if (icon == NULL || !icon->modern)
        return 0;
    count = SpriteAtlas_CountPrefix(&icon->atlas, state_prefix(icon->state));
    if (count == 0 && icon->state != HEALTH_ICON_IDLE)
        count = SpriteAtlas_CountPrefix(&icon->atlas, "idle");
    return count;
}

void HealthIcon_OnBeat(
    HealthIcon *icon,
    s32 beat,
    boolean player,
    HealthIconBounceStyle style)
{
    float s;
    float other;

    if (icon == NULL || !icon->loaded || !(icon->flags & HEALTH_MAP_SHOULD_BOP))
        return;

    if (style == HEALTH_ICON_BOUNCE_CLASSIC) {
        icon->bounce_scale = 1.20f;
        icon->bounce_target = 1.0f;
        return;
    }

    s = (beat & 1) == 0 ? 0.85f : 1.20f;
    other = 2.0f - s;
    icon->bounce_target = player ? s : other;
}

void HealthIcon_Tick(
    HealthIcon *icon,
    fixed_t elapsed,
    s16 health,
    boolean player,
    HealthIconBounceStyle style)
{
    u8 next_state;
    float dt;

    if (icon == NULL || !icon->loaded)
        return;

    next_state = desired_state(health, player);
    if (next_state != icon->state) {
        icon->state = next_state;
        icon->frame_index = 0;
        icon->frame_timer = 0;
    }

    dt = (float)elapsed / (float)FIXED_UNIT;
    if (style == HEALTH_ICON_BOUNCE_REWORKED) {
        float alpha = 1.0f - expf(-13.0f * dt);
        icon->bounce_scale += (icon->bounce_target - icon->bounce_scale) * alpha;
    } else if (icon->bounce_scale > 1.0f) {
        /* Approximate base-game bop return, capped near the official .175 sec. */
        float alpha = dt / 0.175f;
        if (alpha > 1.0f) alpha = 1.0f;
        icon->bounce_scale += (1.0f - icon->bounce_scale) * alpha;
    }

    if (icon->modern) {
        u16 count = modern_frame_count(icon);
        fixed_t frame_duration = FIXED_DEC(1, 24);
        if (count > 1) {
            icon->frame_timer += elapsed;
            while (icon->frame_timer >= frame_duration) {
                icon->frame_timer -= frame_duration;
                icon->frame_index = (u16)((icon->frame_index + 1u) % count);
            }
        } else {
            icon->frame_index = 0;
        }
    }
}

static float target_center_x(
    float bar_x,
    float bar_w,
    s16 health,
    boolean player,
    HealthIconPositionMode position)
{
    float ratio = (float)health / 20000.0f;
    float split;
    if (ratio < 0.0f) ratio = 0.0f;
    if (ratio > 1.0f) ratio = 1.0f;

    if (position == HEALTH_ICON_POSITION_CORNERS)
        return player ? bar_x + bar_w : bar_x;
    if (position == HEALTH_ICON_POSITION_DEFAULT)
        return player ? bar_x + bar_w + 50.0f : bar_x - 50.0f;

    split = bar_x + bar_w * ratio;
    return player ? split + 13.0f : split - 13.0f;
}

void HealthIcon_Draw(
    GSGLOBAL *gs,
    const HealthIcon *icon,
    float bar_x,
    float bar_y,
    float bar_w,
    float bar_h,
    s16 health,
    boolean player,
    HealthIconPositionMode position,
    float opacity,
    int z)
{
    float target_size;
    float cx;
    float cy;
    float draw_scale;
    float x;
    float y;
    boolean flip;
    u8 alpha;
    u64 color;

    if (gs == NULL || icon == NULL || !icon->loaded)
        return;
    if (opacity < 0.0f) opacity = 0.0f;
    if (opacity > 1.0f) opacity = 1.0f;
    alpha = (u8)(opacity * 128.0f + 0.5f);
    color = GS_SETREG_RGBAQ(0x80, 0x80, 0x80, alpha, 0);
    target_size = HEALTH_ICON_LOGICAL_SIZE * icon->scale * icon->bounce_scale;
    cx = target_center_x(bar_x, bar_w, health, player, position) + icon->offset_x;
    cy = bar_y + bar_h * 0.5f + icon->offset_y;
    flip = (icon->flags & HEALTH_MAP_FLIP_X) != 0;

    if (icon->modern) {
        const char *prefix = state_prefix(icon->state);
        s32 frame;
        const AtlasFrame *record;
        u16 count = SpriteAtlas_CountPrefix(&icon->atlas, prefix);
        if (count == 0) {
            prefix = "idle";
            count = SpriteAtlas_CountPrefix(&icon->atlas, prefix);
        }
        if (count == 0)
            return;
        frame = SpriteAtlas_FindPrefixNth(&icon->atlas, prefix, icon->frame_index % count);
        if (frame < 0)
            return;
        record = &icon->atlas.frames[frame];
        if (record->frame_height == 0)
            return;
        draw_scale = target_size / (float)record->frame_height;
        x = cx - ((float)record->frame_width * draw_scale * 0.5f);
        y = cy - ((float)record->frame_height * draw_scale * 0.5f);
        SpriteAtlas_DrawFrameEx(
            gs, &icon->atlas, (u16)frame,
            x, y, draw_scale, draw_scale, flip, false, z, color);
    } else {
        float frame_h = (float)icon->texture.texture.Height;
        float frame_w = frame_h;
        u16 frames;
        u16 frame = icon->state;
        float u1;
        float u2;
        if (frame_h <= 0.0f)
            return;
        frames = (u16)((float)icon->texture.texture.Width / frame_w + 0.5f);
        if (frames == 0)
            frames = 1;
        if (frame >= frames)
            frame = 0;
        draw_scale = target_size / frame_h;
        x = cx - target_size * 0.5f;
        y = cy - target_size * 0.5f;
        u1 = frame_w * frame;
        u2 = u1 + frame_w;
        if (flip) {
            float tmp = u1;
            u1 = u2;
            u2 = tmp;
        }
        TextureAsset_Draw(
            gs, &icon->texture,
            x, y, x + target_size, y + target_size,
            u1, 0.0f, u2, frame_h,
            z, color);
    }
}
