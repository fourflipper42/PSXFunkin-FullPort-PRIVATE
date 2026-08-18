#ifndef FNF_PS2_STAGE_H
#define FNF_PS2_STAGE_H

#include "sprite_atlas.h"
#include "fixed.h"

typedef struct StageCharacterSlot {
    float x;
    float y;
    s32 z_index;
    float scale;
    float camera_x;
    float camera_y;
    float scroll_x;
    float scroll_y;
    float alpha;
    float angle;
    float reserved;
} __attribute__((packed)) StageCharacterSlot;

typedef struct StageAnimData {
    u32 name_offset;
    u32 prefix_offset;
    float offset_x;
    float offset_y;
    u16 frame_rate;
    u16 flags;
    u32 index_offset;
    u16 index_count;
    u16 reserved;
} __attribute__((packed)) StageAnimData;

typedef struct StagePropData {
    s32 z_index;
    u32 flags;
    float x;
    float y;
    float scale_x;
    float scale_y;
    float scroll_x;
    float scroll_y;
    float alpha;
    float angle;
    float dance_every;
    u32 starting_name_offset;
    u16 animation_count;
    u16 reserved;
    u32 animation_start;
    u32 color;
} __attribute__((packed)) StagePropData;

typedef struct StagePropRuntime {
    TextureAsset texture;
    SpriteAtlas atlas;
    s16 current_animation;
    u16 current_frame;
    fixed_t frame_timer;
    boolean finished;
    boolean dance_right;
    boolean loaded;
} StagePropRuntime;

typedef struct Stage {
    void *config_blob;
    size_t config_size;
    StageCharacterSlot bf;
    StageCharacterSlot dad;
    StageCharacterSlot gf;
    StagePropData *props;
    StageAnimData *animations;
    u16 *frame_indices;
    char *strings;
    StagePropRuntime *runtime;
    u16 *draw_order;
    u16 prop_count;
    u32 animation_count;
    u32 indices_count;
    u32 string_bytes;
    float camera_zoom;
    boolean loaded;
    char base_path[192];
} Stage;

typedef struct StageCamera {
    float scroll_x;
    float scroll_y;
    float zoom;
} StageCamera;

boolean Stage_Load(GSGLOBAL *gs, Stage *stage, const char *base_path);
void Stage_Forget(Stage *stage);
void Stage_Tick(Stage *stage);
void Stage_Beat(Stage *stage, s32 beat);
void Stage_DrawRange(
    GSGLOBAL *gs,
    const Stage *stage,
    const StageCamera *camera,
    s32 z_min,
    s32 z_max);
const StageCharacterSlot *Stage_PlayerSlot(const Stage *stage);
const StageCharacterSlot *Stage_OpponentSlot(const Stage *stage);
const StageCharacterSlot *Stage_GirlfriendSlot(const Stage *stage);
float Stage_CameraZoom(const Stage *stage);

#endif
