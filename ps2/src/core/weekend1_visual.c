#include "weekend1_visual.h"

#include "sprite_atlas.h"
#include <string.h>

#define WEEKEND1_CAN_MAX 8
#define WEEKEND1_EFFECT_MAX 8
#define WEEKEND1_FRAME_TIME FIXED_DEC(1, 24)

typedef enum Weekend1CanState {
    WEEKEND1_CAN_UNUSED = 0,
    WEEKEND1_CAN_ARC,
    WEEKEND1_CAN_SHOT,
    WEEKEND1_CAN_IMPACT
} Weekend1CanState;

typedef enum Weekend1EffectKind {
    WEEKEND1_EFFECT_NONE = 0,
    WEEKEND1_EFFECT_SHOT,
    WEEKEND1_EFFECT_IMPACT
} Weekend1EffectKind;

typedef struct Weekend1CanVisual {
    Weekend1CanState state;
    u16 frame;
    fixed_t timer;
    boolean shot_effect_spawned;
} Weekend1CanVisual;

typedef struct Weekend1EffectVisual {
    Weekend1EffectKind kind;
    u16 frame;
    fixed_t timer;
    float offset_x;
    float offset_y;
} Weekend1EffectVisual;

static boolean g_enabled;
static boolean g_load_attempted;
static boolean g_can_loaded;
static boolean g_shot_loaded;
static boolean g_impact_loaded;
static SpriteAtlas g_can_atlas;
static SpriteAtlas g_shot_atlas;
static SpriteAtlas g_impact_atlas;
static Weekend1CanVisual g_cans[WEEKEND1_CAN_MAX];
static Weekend1EffectVisual g_effects[WEEKEND1_EFFECT_MAX];

static const char *can_prefix(const Weekend1CanVisual *can)
{
    if (can == NULL)
        return NULL;
    switch (can->state) {
        case WEEKEND1_CAN_ARC: return "Can Start";
        case WEEKEND1_CAN_SHOT: return "Can Shot";
        case WEEKEND1_CAN_IMPACT: return "Hit Pico";
        default: return NULL;
    }
}

static const char *effect_prefix(Weekend1EffectKind kind)
{
    switch (kind) {
        case WEEKEND1_EFFECT_SHOT: return "Explosion 1 movie0";
        case WEEKEND1_EFFECT_IMPACT: return "explosion round 1 short0";
        default: return NULL;
    }
}

static SpriteAtlas *effect_atlas(Weekend1EffectKind kind)
{
    switch (kind) {
        case WEEKEND1_EFFECT_SHOT: return g_shot_loaded ? &g_shot_atlas : NULL;
        case WEEKEND1_EFFECT_IMPACT: return g_impact_loaded ? &g_impact_atlas : NULL;
        default: return NULL;
    }
}

static void reset_can_animation(Weekend1CanVisual *can, Weekend1CanState state)
{
    if (can == NULL)
        return;
    can->state = state;
    can->frame = 0;
    can->timer = 0;
    can->shot_effect_spawned = false;
}

static void spawn_effect(Weekend1EffectKind kind, float offset_x, float offset_y)
{
    int i;
    for (i = 0; i < WEEKEND1_EFFECT_MAX; ++i) {
        if (g_effects[i].kind == WEEKEND1_EFFECT_NONE) {
            g_effects[i].kind = kind;
            g_effects[i].frame = 0;
            g_effects[i].timer = 0;
            g_effects[i].offset_x = offset_x;
            g_effects[i].offset_y = offset_y;
            return;
        }
    }
}

static void load_assets(GSGLOBAL *gs)
{
    if (!g_enabled || g_load_attempted || gs == NULL)
        return;
    g_load_attempted = true;

    g_can_loaded = SpriteAtlas_Load(
        gs,
        &g_can_atlas,
        "\\GAME\\WEEKEND1\\CAN.FPTX;1",
        "\\GAME\\WEEKEND1\\CAN.FATL;1",
        true);
    g_shot_loaded = SpriteAtlas_Load(
        gs,
        &g_shot_atlas,
        "\\GAME\\WEEKEND1\\SHOTEXP.FPTX;1",
        "\\GAME\\WEEKEND1\\SHOTEXP.FATL;1",
        true);
    g_impact_loaded = SpriteAtlas_Load(
        gs,
        &g_impact_atlas,
        "\\GAME\\WEEKEND1\\IMPACTEXP.FPTX;1",
        "\\GAME\\WEEKEND1\\IMPACTEXP.FATL;1",
        true);
}

void Weekend1Visual_Begin2Hot(void)
{
    Weekend1Visual_End();
    g_enabled = true;
}

void Weekend1Visual_End(void)
{
    if (g_can_loaded)
        SpriteAtlas_Forget(&g_can_atlas);
    if (g_shot_loaded)
        SpriteAtlas_Forget(&g_shot_atlas);
    if (g_impact_loaded)
        SpriteAtlas_Forget(&g_impact_atlas);
    memset(&g_can_atlas, 0, sizeof(g_can_atlas));
    memset(&g_shot_atlas, 0, sizeof(g_shot_atlas));
    memset(&g_impact_atlas, 0, sizeof(g_impact_atlas));
    memset(g_cans, 0, sizeof(g_cans));
    memset(g_effects, 0, sizeof(g_effects));
    g_enabled = false;
    g_load_attempted = false;
    g_can_loaded = false;
    g_shot_loaded = false;
    g_impact_loaded = false;
}

void Weekend1Visual_KickCan(void)
{
    int i;
    if (!g_enabled)
        return;
    for (i = 0; i < WEEKEND1_CAN_MAX; ++i) {
        if (g_cans[i].state == WEEKEND1_CAN_UNUSED) {
            reset_can_animation(&g_cans[i], WEEKEND1_CAN_ARC);
            return;
        }
    }
}

void Weekend1Visual_ShootCan(void)
{
    int i;
    if (!g_enabled)
        return;
    for (i = 0; i < WEEKEND1_CAN_MAX; ++i) {
        if (g_cans[i].state == WEEKEND1_CAN_ARC) {
            reset_can_animation(&g_cans[i], WEEKEND1_CAN_SHOT);
            return;
        }
    }
}

void Weekend1Visual_ImpactCan(void)
{
    int i;
    if (!g_enabled)
        return;
    for (i = 0; i < WEEKEND1_CAN_MAX; ++i) {
        if (g_cans[i].state == WEEKEND1_CAN_ARC) {
            /* The source keeps playing Can Start until its natural end, then
             * transitions into Hit Pico. Mark the outcome without snapping. */
            g_cans[i].state = WEEKEND1_CAN_IMPACT;
            return;
        }
    }
}

static void tick_can(Weekend1CanVisual *can, fixed_t elapsed)
{
    const char *prefix;
    u16 count;

    if (can == NULL || can->state == WEEKEND1_CAN_UNUSED || !g_can_loaded)
        return;

    prefix = can_prefix(can);
    count = SpriteAtlas_CountPrefix(&g_can_atlas, prefix);
    if (count == 0) {
        can->state = WEEKEND1_CAN_UNUSED;
        return;
    }

    can->timer += elapsed;
    while (can->timer >= WEEKEND1_FRAME_TIME) {
        can->timer -= WEEKEND1_FRAME_TIME;
        ++can->frame;

        if (can->state == WEEKEND1_CAN_SHOT &&
            can->frame >= 3 && !can->shot_effect_spawned) {
            can->shot_effect_spawned = true;
            spawn_effect(WEEKEND1_EFFECT_SHOT, 150.0f, -250.0f);
        }

        if (can->frame < count)
            continue;

        if (can->state == WEEKEND1_CAN_ARC ||
            can->state == WEEKEND1_CAN_IMPACT) {
            reset_can_animation(can, WEEKEND1_CAN_IMPACT);
            prefix = can_prefix(can);
            count = SpriteAtlas_CountPrefix(&g_can_atlas, prefix);
            if (count == 0)
                can->state = WEEKEND1_CAN_UNUSED;
            continue;
        }

        if (can->state == WEEKEND1_CAN_SHOT) {
            can->state = WEEKEND1_CAN_UNUSED;
            return;
        }

        if (can->state == WEEKEND1_CAN_IMPACT) {
            spawn_effect(WEEKEND1_EFFECT_IMPACT, 750.0f, -100.0f);
            can->state = WEEKEND1_CAN_UNUSED;
            return;
        }
    }
}

static void tick_effect(Weekend1EffectVisual *effect, fixed_t elapsed)
{
    SpriteAtlas *atlas;
    const char *prefix;
    u16 count;

    if (effect == NULL || effect->kind == WEEKEND1_EFFECT_NONE)
        return;
    atlas = effect_atlas(effect->kind);
    prefix = effect_prefix(effect->kind);
    if (atlas == NULL || prefix == NULL)
        return;
    count = SpriteAtlas_CountPrefix(atlas, prefix);
    if (count == 0) {
        effect->kind = WEEKEND1_EFFECT_NONE;
        return;
    }

    effect->timer += elapsed;
    while (effect->timer >= WEEKEND1_FRAME_TIME) {
        effect->timer -= WEEKEND1_FRAME_TIME;
        ++effect->frame;
        if (effect->frame >= count) {
            effect->kind = WEEKEND1_EFFECT_NONE;
            return;
        }
    }
}

void Weekend1Visual_Tick(fixed_t elapsed)
{
    int i;
    if (!g_enabled)
        return;
    for (i = 0; i < WEEKEND1_CAN_MAX; ++i)
        tick_can(&g_cans[i], elapsed);
    for (i = 0; i < WEEKEND1_EFFECT_MAX; ++i)
        tick_effect(&g_effects[i], elapsed);
}

static boolean pile_origin(
    const Stage *stage,
    const StagePropData **pile,
    float *x,
    float *y,
    s32 *z)
{
    s32 index;
    if (pile != NULL) *pile = NULL;
    if (stage == NULL || !stage->loaded)
        return false;
    index = Stage_FindProp(stage, "spraycanPile");
    if (index < 0 || (u16)index >= stage->prop_count)
        return false;
    if (pile != NULL) *pile = &stage->props[index];
    if (x != NULL) *x = stage->props[index].x - 10.0f;
    if (y != NULL) *y = stage->props[index].y - 550.0f;
    if (z != NULL) *z = stage->props[index].z_index - 1;
    return true;
}

static void world_to_screen(
    const StagePropData *pile,
    const StageCamera *camera,
    float world_x,
    float world_y,
    float *screen_x,
    float *screen_y,
    float *scale)
{
    float zoom = camera != NULL ? camera->zoom : 1.0f;
    float world_scale;
    if (zoom <= 0.0f)
        zoom = 1.0f;
    world_scale = 0.5f * zoom;
    if (screen_x != NULL)
        *screen_x = (world_x -
            ((camera != NULL ? camera->scroll_x : 0.0f) * pile->scroll_x)) * world_scale;
    if (screen_y != NULL)
        *screen_y = (world_y -
            ((camera != NULL ? camera->scroll_y : 0.0f) * pile->scroll_y)) * world_scale;
    if (scale != NULL)
        *scale = world_scale;
}

void Weekend1Visual_DrawRange(
    GSGLOBAL *gs,
    const Stage *stage,
    const StageCamera *camera,
    s32 z_min,
    s32 z_max)
{
    const u64 white = GS_SETREG_RGBAQ(0x80, 0x80, 0x80, 0x80, 0);
    const StagePropData *pile;
    float base_x;
    float base_y;
    s32 base_z;
    int i;

    if (!g_enabled || gs == NULL || stage == NULL)
        return;
    load_assets(gs);
    if (!pile_origin(stage, &pile, &base_x, &base_y, &base_z))
        return;

    if (base_z >= z_min && base_z <= z_max && g_can_loaded) {
        for (i = 0; i < WEEKEND1_CAN_MAX; ++i) {
            Weekend1CanVisual *can = &g_cans[i];
            const char *prefix;
            s32 frame_index;
            float x;
            float y;
            float scale;
            if (can->state == WEEKEND1_CAN_UNUSED)
                continue;
            prefix = can_prefix(can);
            frame_index = SpriteAtlas_FindPrefixNth(&g_can_atlas, prefix, can->frame);
            if (frame_index < 0)
                continue;
            world_to_screen(pile, camera, base_x, base_y, &x, &y, &scale);
            SpriteAtlas_DrawFrame(
                gs, &g_can_atlas, (u16)frame_index,
                x, y, scale, scale, 2, white);
        }
    }

    for (i = 0; i < WEEKEND1_EFFECT_MAX; ++i) {
        Weekend1EffectVisual *effect = &g_effects[i];
        SpriteAtlas *atlas;
        const char *prefix;
        s32 frame_index;
        float x;
        float y;
        float scale;
        s32 effect_z = base_z + 2;

        if (effect->kind == WEEKEND1_EFFECT_NONE ||
            effect_z < z_min || effect_z > z_max)
            continue;
        atlas = effect_atlas(effect->kind);
        prefix = effect_prefix(effect->kind);
        if (atlas == NULL || prefix == NULL)
            continue;
        frame_index = SpriteAtlas_FindPrefixNth(atlas, prefix, effect->frame);
        if (frame_index < 0)
            continue;
        world_to_screen(
            pile,
            camera,
            base_x + effect->offset_x,
            base_y + effect->offset_y,
            &x,
            &y,
            &scale);
        SpriteAtlas_DrawFrame(
            gs, atlas, (u16)frame_index,
            x, y, scale, scale, 2, white);
    }
}
