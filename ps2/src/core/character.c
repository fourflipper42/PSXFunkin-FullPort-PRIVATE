#include "character.h"

#include "asset_file.h"
#include "mem.h"
#include "timer.h"
#include <string.h>

typedef struct CharacterHeader {
    char magic[4];
    u16 version;
    u16 animation_count;
    u32 string_bytes;
    u32 indices_count;
    u32 starting_animation_offset;
    float scale;
    float global_x;
    float global_y;
    float sing_time;
    float dance_every;
    u32 flags;
    u32 record_size;
} __attribute__((packed)) CharacterHeader;

#define CHARACTER_VERSION 1
#define CHARACTER_FLAG_FLIP_X (1u << 0)
#define CHARACTER_FLAG_PIXEL  (1u << 1)
#define CHARACTER_ANIM_LOOPED (1u << 0)
#define CHARACTER_ANIM_FLIP_X (1u << 1)
#define CHARACTER_ANIM_FLIP_Y (1u << 2)
#define CHARACTER_NO_STRING 0xFFFFFFFFu

static const char *character_string(const Character *character, u32 offset)
{
    if (character == NULL || !character->loaded || offset == CHARACTER_NO_STRING ||
        offset >= character->string_bytes)
        return NULL;
    return character->strings + offset;
}

static u16 animation_frame_count(const Character *character, const CharacterAnimData *anim)
{
    const char *prefix;
    if (character == NULL || anim == NULL)
        return 0;
    if (anim->index_count != 0)
        return anim->index_count;
    prefix = character_string(character, anim->prefix_offset);
    return SpriteAtlas_CountPrefix(&character->atlas, prefix);
}

static s32 animation_atlas_frame(
    const Character *character,
    const CharacterAnimData *anim,
    u16 logical_frame)
{
    const char *prefix;
    u16 prefix_index;

    if (character == NULL || anim == NULL)
        return -1;
    prefix = character_string(character, anim->prefix_offset);
    if (prefix == NULL)
        return -1;

    if (anim->index_count != 0) {
        if (logical_frame >= anim->index_count)
            return -1;
        prefix_index = character->frame_indices[anim->index_offset + logical_frame];
    } else {
        prefix_index = logical_frame;
    }
    return SpriteAtlas_FindPrefixNth(&character->atlas, prefix, prefix_index);
}

boolean Character_Load(
    GSGLOBAL *gs,
    Character *character,
    const char *config_path,
    const char *texture_path,
    const char *frames_path)
{
    AssetFile file;
    CharacterHeader *header;
    size_t records_bytes;
    size_t indices_bytes;
    size_t minimum;
    size_t got;
    const char *starting;

    if (gs == NULL || character == NULL || config_path == NULL ||
        texture_path == NULL || frames_path == NULL)
        return false;

    memset(character, 0, sizeof(*character));
    character->current_animation = -1;
    memset(&file, 0, sizeof(file));

    if (!SpriteAtlas_Load(gs, &character->atlas, texture_path, frames_path, true))
        return false;

    if (!AssetFile_Open(&file, config_path))
        goto fail;
    character->config_size = AssetFile_Size(&file);
    if (character->config_size < sizeof(CharacterHeader))
        goto fail;

    character->config_blob = Mem_Alloc(character->config_size);
    if (character->config_blob == NULL)
        goto fail;
    got = AssetFile_Read(&file, character->config_blob, character->config_size);
    AssetFile_Close(&file);
    if (got != character->config_size)
        goto fail;

    header = (CharacterHeader *)character->config_blob;
    if (memcmp(header->magic, "FCHR", 4) != 0 ||
        header->version != CHARACTER_VERSION ||
        header->animation_count == 0 ||
        header->record_size != sizeof(CharacterAnimData))
        goto fail;

    records_bytes = (size_t)header->animation_count * sizeof(CharacterAnimData);
    indices_bytes = (size_t)header->indices_count * sizeof(u16);
    minimum = sizeof(CharacterHeader) + records_bytes + indices_bytes + header->string_bytes;
    if (minimum > character->config_size)
        goto fail;

    character->animations = (CharacterAnimData *)((u8 *)character->config_blob + sizeof(CharacterHeader));
    character->frame_indices = (u16 *)((u8 *)character->animations + records_bytes);
    character->strings = (char *)((u8 *)character->frame_indices + indices_bytes);
    character->animation_count = header->animation_count;
    character->string_bytes = header->string_bytes;
    character->scale = header->scale;
    character->global_x = header->global_x;
    character->global_y = header->global_y;
    character->sing_time = header->sing_time;
    character->dance_every = header->dance_every;
    character->flags = header->flags;
    character->loaded = true;

    starting = character_string(character, header->starting_animation_offset);
    if (starting == NULL || !Character_Play(character, starting, true))
        Character_Dance(character, true);
    return true;

fail:
    AssetFile_Close(&file);
    if (character->config_blob != NULL)
        Mem_Free(character->config_blob);
    SpriteAtlas_Forget(&character->atlas);
    memset(character, 0, sizeof(*character));
    character->current_animation = -1;
    return false;
}

void Character_Forget(Character *character)
{
    if (character == NULL)
        return;
    if (character->config_blob != NULL)
        Mem_Free(character->config_blob);
    SpriteAtlas_Forget(&character->atlas);
    memset(character, 0, sizeof(*character));
    character->current_animation = -1;
}

s32 Character_FindAnimation(const Character *character, const char *name)
{
    u16 i;
    if (character == NULL || !character->loaded || name == NULL)
        return -1;
    for (i = 0; i < character->animation_count; ++i) {
        const char *anim_name = character_string(character, character->animations[i].name_offset);
        if (anim_name != NULL && strcmp(anim_name, name) == 0)
            return (s32)i;
    }
    return -1;
}

boolean Character_HasAnimation(const Character *character, const char *name)
{
    return Character_FindAnimation(character, name) >= 0;
}

boolean Character_Play(Character *character, const char *name, boolean restart)
{
    s32 index;
    if (character == NULL || !character->loaded || name == NULL)
        return false;

    index = Character_FindAnimation(character, name);
    if (index < 0)
        return false;
    if (!restart && character->current_animation == index)
        return true;

    character->current_animation = (s16)index;
    character->current_frame = 0;
    character->frame_timer = 0;
    character->finished = false;
    return true;
}

void Character_Dance(Character *character, boolean restart)
{
    if (character == NULL || !character->loaded)
        return;

    if (Character_HasAnimation(character, "danceLeft") &&
        Character_HasAnimation(character, "danceRight")) {
        const char *next = character->dance_right ? "danceRight" : "danceLeft";
        character->dance_right = !character->dance_right;
        Character_Play(character, next, restart);
    } else if (!Character_Play(character, "idle", restart)) {
        if (character->animation_count > 0) {
            const char *fallback = character_string(character, character->animations[0].name_offset);
            if (fallback != NULL)
                Character_Play(character, fallback, restart);
        }
    }
}

void Character_Tick(Character *character)
{
    CharacterAnimData *anim;
    u16 count;
    fixed_t frame_duration;

    if (character == NULL || !character->loaded || character->current_animation < 0)
        return;

    anim = &character->animations[character->current_animation];
    count = animation_frame_count(character, anim);
    if (count <= 1 || anim->frame_rate == 0)
        return;

    frame_duration = FIXED_DEC(1, anim->frame_rate);
    character->frame_timer += timer_dt;
    while (character->frame_timer >= frame_duration) {
        character->frame_timer -= frame_duration;
        ++character->current_frame;
        if (character->current_frame >= count) {
            if (anim->flags & CHARACTER_ANIM_LOOPED) {
                character->current_frame = 0;
            } else {
                character->current_frame = count - 1;
                character->finished = true;
                character->frame_timer = 0;
                break;
            }
        }
    }
}

void Character_Draw(
    GSGLOBAL *gs,
    const Character *character,
    float stage_x,
    float stage_y,
    float stage_scale,
    int z,
    u64 color)
{
    const CharacterAnimData *anim;
    s32 frame_index;
    float draw_scale;
    float x;
    float y;
    boolean flip_x;
    boolean flip_y;

    if (gs == NULL || character == NULL || !character->loaded || character->current_animation < 0)
        return;

    anim = &character->animations[character->current_animation];
    frame_index = animation_atlas_frame(character, anim, character->current_frame);
    if (frame_index < 0)
        return;

    draw_scale = character->scale * stage_scale;
    x = stage_x + (character->global_x - anim->offset_x) * draw_scale;
    y = stage_y + (character->global_y - anim->offset_y) * draw_scale;
    flip_x = ((character->flags & CHARACTER_FLAG_FLIP_X) != 0) ^
        ((anim->flags & CHARACTER_ANIM_FLIP_X) != 0);
    flip_y = (anim->flags & CHARACTER_ANIM_FLIP_Y) != 0;

    SpriteAtlas_DrawFrameEx(
        gs,
        &character->atlas,
        (u16)frame_index,
        x,
        y,
        draw_scale,
        draw_scale,
        flip_x,
        flip_y,
        z,
        color);
}

const char *Character_CurrentAnimationName(const Character *character)
{
    if (character == NULL || !character->loaded || character->current_animation < 0)
        return NULL;
    return character_string(character, character->animations[character->current_animation].name_offset);
}

boolean Character_AnimationFinished(const Character *character)
{
    return character != NULL && character->loaded && character->finished;
}
