#ifndef FNF_PS2_HEALTH_ICON_H
#define FNF_PS2_HEALTH_ICON_H

#include "fixed.h"
#include "sprite_atlas.h"
#include "texture_asset.h"

typedef enum HealthIconPositionMode {
    HEALTH_ICON_POSITION_DEFAULT = 0,
    HEALTH_ICON_POSITION_CORNERS,
    HEALTH_ICON_POSITION_CLASSIC
} HealthIconPositionMode;

typedef enum HealthIconBounceStyle {
    HEALTH_ICON_BOUNCE_REWORKED = 0,
    HEALTH_ICON_BOUNCE_CLASSIC
} HealthIconBounceStyle;

typedef struct HealthIcon {
    SpriteAtlas atlas;
    TextureAsset texture;
    char id[64];
    float scale;
    float offset_x;
    float offset_y;
    float bounce_scale;
    float bounce_target;
    fixed_t frame_timer;
    u16 frame_index;
    u16 flags;
    u8 state;
    boolean modern;
    boolean loaded;
} HealthIcon;

boolean HealthIcon_Load(
    GSGLOBAL *gs,
    HealthIcon *icon,
    const char *character_base);
void HealthIcon_Forget(HealthIcon *icon);
void HealthIcon_OnBeat(
    HealthIcon *icon,
    s32 beat,
    boolean player,
    HealthIconBounceStyle style);
void HealthIcon_Tick(
    HealthIcon *icon,
    fixed_t elapsed,
    s16 health,
    boolean player,
    HealthIconBounceStyle style);
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
    int z);

#endif
