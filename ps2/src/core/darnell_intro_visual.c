#include "darnell_intro_visual.h"

#include "sprite_atlas.h"
#include <string.h>

#define DARNELL_FRAME_TIME FIXED_DEC(1, 24)

typedef enum DarnellCanMotion {
    DARNELL_CAN_HIDDEN = 0,
    DARNELL_CAN_UP,
    DARNELL_CAN_FORWARD
} DarnellCanMotion;

static boolean g_enabled;
static boolean g_load_attempted;
static boolean g_intro_loaded;
static boolean g_can_loaded;
static boolean g_explosion_loaded;
static SpriteAtlas g_intro_atlas;
static SpriteAtlas g_can_atlas;
static SpriteAtlas g_explosion_atlas;
static DarnellCanMotion g_intro_motion;
static u16 g_intro_frame;
static fixed_t g_intro_timer;
static boolean g_shot_visible;
static u16 g_shot_frame;
static fixed_t g_shot_timer;
static boolean g_explosion_visible;
static u16 g_explosion_frame;
static fixed_t g_explosion_timer;

static const char *intro_prefix(void)
{
    switch (g_intro_motion) {
        case DARNELL_CAN_UP: return "can kicked up0";
        case DARNELL_CAN_FORWARD: return "can kick quick0";
        default: return NULL;
    }
}

static void load_assets(GSGLOBAL *gs)
{
    if (!g_enabled || g_load_attempted || gs == NULL)
        return;
    g_load_attempted = true;
    g_intro_loaded = SpriteAtlas_Load(
        gs, &g_intro_atlas,
        "\\GAME\\WEEKEND1\\INTROCAN.FPTX;1",
        "\\GAME\\WEEKEND1\\INTROCAN.FATL;1",
        true);
    g_can_loaded = SpriteAtlas_Load(
        gs, &g_can_atlas,
        "\\GAME\\WEEKEND1\\CAN.FPTX;1",
        "\\GAME\\WEEKEND1\\CAN.FATL;1",
        true);
    g_explosion_loaded = SpriteAtlas_Load(
        gs, &g_explosion_atlas,
        "\\GAME\\WEEKEND1\\SHOTEXP.FPTX;1",
        "\\GAME\\WEEKEND1\\SHOTEXP.FATL;1",
        true);
}

void DarnellIntroVisual_Begin(void)
{
    DarnellIntroVisual_End();
    g_enabled = true;
}

void DarnellIntroVisual_End(void)
{
    if (g_intro_loaded) SpriteAtlas_Forget(&g_intro_atlas);
    if (g_can_loaded) SpriteAtlas_Forget(&g_can_atlas);
    if (g_explosion_loaded) SpriteAtlas_Forget(&g_explosion_atlas);
    memset(&g_intro_atlas, 0, sizeof(g_intro_atlas));
    memset(&g_can_atlas, 0, sizeof(g_can_atlas));
    memset(&g_explosion_atlas, 0, sizeof(g_explosion_atlas));
    g_enabled = false;
    g_load_attempted = false;
    g_intro_loaded = false;
    g_can_loaded = false;
    g_explosion_loaded = false;
    g_intro_motion = DARNELL_CAN_HIDDEN;
    g_intro_frame = 0;
    g_intro_timer = 0;
    g_shot_visible = false;
    g_shot_frame = 0;
    g_shot_timer = 0;
    g_explosion_visible = false;
    g_explosion_frame = 0;
    g_explosion_timer = 0;
}

void DarnellIntroVisual_KickUp(void)
{
    if (!g_enabled) return;
    g_intro_motion = DARNELL_CAN_UP;
    g_intro_frame = 0;
    g_intro_timer = 0;
}

void DarnellIntroVisual_KneeForward(void)
{
    if (!g_enabled) return;
    g_intro_motion = DARNELL_CAN_FORWARD;
    g_intro_frame = 0;
    g_intro_timer = 0;
}

void DarnellIntroVisual_Shoot(void)
{
    if (!g_enabled) return;
    g_intro_motion = DARNELL_CAN_HIDDEN;
    g_shot_visible = true;
    g_shot_frame = 0;
    g_shot_timer = 0;
    g_explosion_visible = false;
}

static void tick_intro(fixed_t elapsed)
{
    const char *prefix;
    u16 count;
    if (g_intro_motion == DARNELL_CAN_HIDDEN || !g_intro_loaded)
        return;
    prefix = intro_prefix();
    count = SpriteAtlas_CountPrefix(&g_intro_atlas, prefix);
    if (count == 0) return;
    g_intro_timer += elapsed;
    while (g_intro_timer >= DARNELL_FRAME_TIME) {
        g_intro_timer -= DARNELL_FRAME_TIME;
        if (g_intro_frame + 1 < count)
            ++g_intro_frame;
        else
            break;
    }
}

static void tick_shot(fixed_t elapsed)
{
    u16 count;
    if (!g_shot_visible || !g_can_loaded)
        return;
    count = SpriteAtlas_CountPrefix(&g_can_atlas, "Can Shot");
    if (count == 0) {
        g_shot_visible = false;
        return;
    }
    g_shot_timer += elapsed;
    while (g_shot_timer >= DARNELL_FRAME_TIME) {
        g_shot_timer -= DARNELL_FRAME_TIME;
        ++g_shot_frame;
        if (g_shot_frame == 3) {
            g_explosion_visible = true;
            g_explosion_frame = 0;
            g_explosion_timer = 0;
        }
        if (g_shot_frame >= count) {
            g_shot_visible = false;
            break;
        }
    }
}

static void tick_explosion(fixed_t elapsed)
{
    u16 count;
    if (!g_explosion_visible || !g_explosion_loaded)
        return;
    count = SpriteAtlas_CountPrefix(&g_explosion_atlas, "Explosion 1 movie0");
    if (count == 0) {
        g_explosion_visible = false;
        return;
    }
    g_explosion_timer += elapsed;
    while (g_explosion_timer >= DARNELL_FRAME_TIME) {
        g_explosion_timer -= DARNELL_FRAME_TIME;
        ++g_explosion_frame;
        if (g_explosion_frame >= count) {
            g_explosion_visible = false;
            break;
        }
    }
}

void DarnellIntroVisual_Tick(fixed_t elapsed)
{
    if (!g_enabled) return;
    tick_intro(elapsed);
    tick_shot(elapsed);
    tick_explosion(elapsed);
}

static boolean pile(
    const Stage *stage,
    const StagePropData **prop,
    float *x,
    float *y,
    s32 *z)
{
    s32 index;
    if (stage == NULL || !stage->loaded) return false;
    index = Stage_FindProp(stage, "spraycanPile");
    if (index < 0 || (u16)index >= stage->prop_count) return false;
    if (prop != NULL) *prop = &stage->props[index];
    if (x != NULL) *x = stage->props[index].x;
    if (y != NULL) *y = stage->props[index].y;
    if (z != NULL) *z = stage->props[index].z_index;
    return true;
}

static void project(
    const StagePropData *prop,
    const StageCamera *camera,
    float wx,
    float wy,
    float *x,
    float *y,
    float *scale)
{
    float zoom = camera != NULL ? camera->zoom : 1.0f;
    float s;
    if (zoom <= 0.0f) zoom = 1.0f;
    s = 0.5f * zoom;
    if (x != NULL) *x = (wx - ((camera != NULL ? camera->scroll_x : 0.0f) * prop->scroll_x)) * s;
    if (y != NULL) *y = (wy - ((camera != NULL ? camera->scroll_y : 0.0f) * prop->scroll_y)) * s;
    if (scale != NULL) *scale = s;
}

void DarnellIntroVisual_DrawRange(
    GSGLOBAL *gs,
    const Stage *stage,
    const StageCamera *camera,
    s32 z_min,
    s32 z_max)
{
    const u64 white = GS_SETREG_RGBAQ(0x80, 0x80, 0x80, 0x80, 0);
    const StagePropData *prop;
    float px;
    float py;
    s32 pz;
    float x;
    float y;
    float scale;
    s32 frame;

    if (!g_enabled || gs == NULL || !pile(stage, &prop, &px, &py, &pz))
        return;
    load_assets(gs);

    if (g_intro_motion != DARNELL_CAN_HIDDEN && g_intro_loaded &&
        pz - 1 >= z_min && pz - 1 <= z_max) {
        frame = SpriteAtlas_FindPrefixNth(&g_intro_atlas, intro_prefix(), g_intro_frame);
        if (frame >= 0) {
            project(prop, camera, px + 30.0f, py - 320.0f, &x, &y, &scale);
            SpriteAtlas_DrawFrame(gs, &g_intro_atlas, (u16)frame, x, y, scale, scale, 2, white);
        }
    }

    if (g_shot_visible && g_can_loaded && 300 >= z_min && 300 <= z_max) {
        frame = SpriteAtlas_FindPrefixNth(&g_can_atlas, "Can Shot", g_shot_frame);
        if (frame >= 0) {
            project(prop, camera, px - 10.0f, py - 550.0f, &x, &y, &scale);
            SpriteAtlas_DrawFrame(gs, &g_can_atlas, (u16)frame, x, y, scale, scale, 2, white);
        }
    }

    if (g_explosion_visible && g_explosion_loaded && 301 >= z_min && 301 <= z_max) {
        frame = SpriteAtlas_FindPrefixNth(&g_explosion_atlas, "Explosion 1 movie0", g_explosion_frame);
        if (frame >= 0) {
            project(prop, camera, px + 140.0f, py - 800.0f, &x, &y, &scale);
            SpriteAtlas_DrawFrame(gs, &g_explosion_atlas, (u16)frame, x, y, scale, scale, 2, white);
        }
    }
}
