#ifndef FNF_PS2_CHARACTER_H
#define FNF_PS2_CHARACTER_H

#include "sprite_atlas.h"

typedef struct CharacterAnimData {
    u32 name_offset;
    u32 prefix_offset;
    float offset_x;
    float offset_y;
    u16 frame_rate;
    u16 flags;
    u32 index_offset;
    u16 index_count;
    u16 reserved;
} __attribute__((packed)) CharacterAnimData;

typedef struct Character {
    SpriteAtlas atlas;
    void *config_blob;
    size_t config_size;
    CharacterAnimData *animations;
    u16 *frame_indices;
    char *strings;
    u16 animation_count;
    u32 string_bytes;

    float scale;
    float global_x;
    float global_y;
    float sing_time;
    float dance_every;
    u32 flags;

    s16 current_animation;
    u16 current_frame;
    fixed_t frame_timer;
    boolean finished;
    boolean dance_right;
    boolean loaded;
} Character;

boolean Character_Load(
    GSGLOBAL *gs,
    Character *character,
    const char *config_path,
    const char *texture_path,
    const char *frames_path);
void Character_Forget(Character *character);
s32 Character_FindAnimation(const Character *character, const char *name);
boolean Character_HasAnimation(const Character *character, const char *name);
boolean Character_Play(Character *character, const char *name, boolean restart);
void Character_Dance(Character *character, boolean restart);
void Character_Tick(Character *character);
void Character_Draw(
    GSGLOBAL *gs,
    const Character *character,
    float stage_x,
    float stage_y,
    float stage_scale,
    int z,
    u64 color);
const char *Character_CurrentAnimationName(const Character *character);
boolean Character_AnimationFinished(const Character *character);

#endif
