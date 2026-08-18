#include "sserafim_runtime.h"

#include "mem.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SSERAFIM_EXTRA_COUNT 3
#define SSERAFIM_CAST_COUNT 6
#define SSERAFIM_EXTRA_Z 1000

typedef struct SserafimExtra {
    Character character;
    float target_x;
    float target_y;
    float scroll_x;
    float scroll_y;
    boolean visible;
    boolean loaded;
} SserafimExtra;

static Stage *g_stage;
static SserafimExtra g_extra[SSERAFIM_EXTRA_COUNT];
static boolean g_active;
static boolean g_visible[SSERAFIM_CAST_COUNT];
static boolean g_singing[SSERAFIM_CAST_COUNT];
static float g_saved_bf_alpha;
static float g_saved_dad_alpha;
static float g_saved_gf_alpha;
static float g_dark_amount;
static float g_dark_start;
static float g_dark_target;
static fixed_t g_dark_time;
static fixed_t g_dark_duration;
static float g_light_amount;
static fixed_t g_light_time;
static fixed_t g_light_duration;
static boolean g_pulse_enabled;
static float g_pulse_intensity[4];
static float g_pulse_duration[4];
static u8 g_pulse_count;
static u8 g_pulse_index;
static fixed_t g_pulse_time;
static fixed_t g_flash_time;
static fixed_t g_flash_duration;

boolean Character_LoadCore(
    GSGLOBAL *gs,
    Character *character,
    const char *config_path,
    const char *texture_path,
    const char *frames_path);
void Character_ForgetCore(Character *character);

static boolean contains_case(const char *text, const char *needle)
{
    size_t i;
    size_t n;
    if (text == NULL || needle == NULL)
        return false;
    n = strlen(needle);
    if (n == 0)
        return true;
    for (; *text != '\0'; ++text) {
        for (i = 0; i < n; ++i) {
            if (text[i] == '\0' ||
                toupper((unsigned char)text[i]) != toupper((unsigned char)needle[i]))
                break;
        }
        if (i == n)
            return true;
    }
    return false;
}

static boolean json_bool(const char *json, const char *key, boolean fallback)
{
    char pattern[64];
    const char *p;
    if (json == NULL || key == NULL)
        return fallback;
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    p = strstr(json, pattern);
    if (p == NULL)
        return fallback;
    p = strchr(p + strlen(pattern), ':');
    if (p == NULL)
        return fallback;
    ++p;
    while (*p != '\0' && isspace((unsigned char)*p)) ++p;
    if (strncmp(p, "true", 4) == 0) return true;
    if (strncmp(p, "false", 5) == 0) return false;
    return fallback;
}

static float json_float(const char *json, const char *key, float fallback)
{
    char pattern[64];
    const char *p;
    char *end;
    double value;
    if (json == NULL || key == NULL)
        return fallback;
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    p = strstr(json, pattern);
    if (p == NULL)
        return fallback;
    p = strchr(p + strlen(pattern), ':');
    if (p == NULL)
        return fallback;
    value = strtod(p + 1, &end);
    if (end == p + 1)
        return fallback;
    return (float)value;
}

static int json_bool_array(
    const char *json,
    const char *key,
    boolean *out,
    int max_count)
{
    char pattern[64];
    const char *p;
    int count = 0;
    if (json == NULL || key == NULL || out == NULL || max_count <= 0)
        return 0;
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    p = strstr(json, pattern);
    if (p == NULL)
        return 0;
    p = strchr(p + strlen(pattern), '[');
    if (p == NULL)
        return 0;
    ++p;
    while (*p != '\0' && *p != ']' && count < max_count) {
        while (*p != '\0' && *p != ']' && *p != 't' && *p != 'f') ++p;
        if (strncmp(p, "true", 4) == 0) {
            out[count++] = true;
            p += 4;
        } else if (strncmp(p, "false", 5) == 0) {
            out[count++] = false;
            p += 5;
        } else if (*p != ']') {
            ++p;
        }
    }
    return count;
}

static int json_float_array(
    const char *json,
    const char *key,
    float *out,
    int max_count)
{
    char pattern[64];
    const char *p;
    char *end;
    int count = 0;
    if (json == NULL || key == NULL || out == NULL || max_count <= 0)
        return 0;
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    p = strstr(json, pattern);
    if (p == NULL)
        return 0;
    p = strchr(p + strlen(pattern), '[');
    if (p == NULL)
        return 0;
    ++p;
    while (*p != '\0' && *p != ']' && count < max_count) {
        while (*p != '\0' && *p != ']' &&
            *p != '-' && *p != '+' && *p != '.' && !isdigit((unsigned char)*p)) ++p;
        if (*p == ']') break;
        out[count] = (float)strtod(p, &end);
        if (end == p) {
            ++p;
            continue;
        }
        ++count;
        p = end;
    }
    return count;
}

static void set_prop_alpha(const char *name, float alpha)
{
    s32 index;
    if (g_stage == NULL || name == NULL)
        return;
    index = Stage_FindProp(g_stage, name);
    if (index < 0 || (u16)index >= g_stage->prop_count)
        return;
    if (alpha < 0.0f) alpha = 0.0f;
    if (alpha > 1.0f) alpha = 1.0f;
    g_stage->props[index].alpha = alpha;
}

static void apply_visibility(void)
{
    if (!g_active || g_stage == NULL)
        return;
    g_extra[0].visible = g_visible[0];
    g_extra[1].visible = g_visible[2];
    g_extra[2].visible = g_visible[3];
    g_stage->dad.alpha = g_visible[1] ? g_saved_dad_alpha : 0.0f;
    g_stage->bf.alpha = g_visible[4] ? g_saved_bf_alpha : 0.0f;
    g_stage->gf.alpha = g_visible[5] ? g_saved_gf_alpha : 0.0f;
}

static boolean load_extra(
    GSGLOBAL *gs,
    SserafimExtra *extra,
    const char *id,
    float target_x,
    float target_y,
    float scroll_x,
    float scroll_y)
{
    char config[256];
    char texture[256];
    char frames[256];
    if (gs == NULL || extra == NULL || id == NULL)
        return false;
    memset(extra, 0, sizeof(*extra));
    snprintf(config, sizeof(config), "\\GAME\\CHAR\\%s\\CHAR.FCHR;1", id);
    snprintf(texture, sizeof(texture), "\\GAME\\CHAR\\%s\\ATLAS.FPTX;1", id);
    snprintf(frames, sizeof(frames), "\\GAME\\CHAR\\%s\\ATLAS.FATL;1", id);
    if (!Character_LoadCore(gs, &extra->character, config, texture, frames))
        return false;
    extra->target_x = target_x;
    extra->target_y = target_y;
    extra->scroll_x = scroll_x;
    extra->scroll_y = scroll_y;
    extra->loaded = true;
    return true;
}

boolean SserafimRuntime_Begin(GSGLOBAL *gs, Stage *stage, const char *base_path)
{
    static const boolean base_visible[SSERAFIM_CAST_COUNT] = {
        true, false, false, false, false, false
    };
    static const boolean base_singing[SSERAFIM_CAST_COUNT] = {
        false, false, false, false, false, false
    };

    SserafimRuntime_End();
    if (gs == NULL || stage == NULL || !stage->loaded ||
        !contains_case(base_path, "SSERAFIM"))
        return false;

    g_stage = stage;
    g_saved_bf_alpha = stage->bf.alpha;
    g_saved_dad_alpha = stage->dad.alpha;
    g_saved_gf_alpha = stage->gf.alpha;

    if (!load_extra(gs, &g_extra[0], "SSERAFIM-YUNJIN", -621.0f, 154.0f, 0.95f, 0.95f) ||
        !load_extra(gs, &g_extra[1], "SSERAFIM-CHAEWON", 687.0f, 98.0f, 0.95f, 0.95f) ||
        !load_extra(gs, &g_extra[2], "SSERAFIM-EUNCHAE", 770.0f, 675.0f, 0.97f, 0.97f)) {
        printf("[PS2] Sserafim extra cast load failed\n");
        SserafimRuntime_End();
        return false;
    }

    memcpy(g_visible, base_visible, sizeof(g_visible));
    memcpy(g_singing, base_singing, sizeof(g_singing));
    g_active = true;
    apply_visibility();
    set_prop_alpha("solidCover", 0.0f);
    set_prop_alpha("truckLight1", 0.0f);
    set_prop_alpha("truckLight2", 0.0f);
    set_prop_alpha("backLightColor", 0.0f);
    set_prop_alpha("backLightWhite", 0.0f);
    printf("[PS2] Sserafim stage runtime loaded\n");
    return true;
}

void SserafimRuntime_End(void)
{
    int i;
    if (g_stage != NULL) {
        g_stage->bf.alpha = g_saved_bf_alpha;
        g_stage->dad.alpha = g_saved_dad_alpha;
        g_stage->gf.alpha = g_saved_gf_alpha;
    }
    for (i = 0; i < SSERAFIM_EXTRA_COUNT; ++i) {
        if (g_extra[i].loaded)
            Character_ForgetCore(&g_extra[i].character);
    }
    memset(g_extra, 0, sizeof(g_extra));
    memset(g_visible, 0, sizeof(g_visible));
    memset(g_singing, 0, sizeof(g_singing));
    g_stage = NULL;
    g_active = false;
    g_dark_amount = 0.0f;
    g_dark_start = 0.0f;
    g_dark_target = 0.0f;
    g_dark_time = 0;
    g_dark_duration = 0;
    g_light_amount = 0.0f;
    g_light_time = 0;
    g_light_duration = 0;
    g_pulse_enabled = false;
    memset(g_pulse_intensity, 0, sizeof(g_pulse_intensity));
    memset(g_pulse_duration, 0, sizeof(g_pulse_duration));
    g_pulse_count = 0;
    g_pulse_index = 0;
    g_pulse_time = 0;
    g_flash_time = 0;
    g_flash_duration = 0;
}

boolean SserafimRuntime_Active(void)
{
    return g_active;
}

static void tick_dark(fixed_t elapsed)
{
    float t;
    if (g_dark_duration <= 0) {
        g_dark_amount = g_dark_target;
        return;
    }
    g_dark_time += elapsed;
    if (g_dark_time >= g_dark_duration) {
        g_dark_time = g_dark_duration;
        g_dark_amount = g_dark_target;
        g_dark_duration = 0;
        return;
    }
    t = (float)g_dark_time / (float)g_dark_duration;
    t = t * t * (3.0f - 2.0f * t);
    g_dark_amount = g_dark_start + (g_dark_target - g_dark_start) * t;
}

static void tick_lights(fixed_t elapsed)
{
    float alpha;
    if (g_light_duration <= 0)
        return;
    g_light_time += elapsed;
    if (g_light_time >= g_light_duration) {
        g_light_duration = 0;
        g_light_amount = 0.0f;
        set_prop_alpha("truckLight1", 0.0f);
        set_prop_alpha("truckLight2", 0.0f);
        return;
    }
    alpha = g_light_amount * (1.0f - (float)g_light_time / (float)g_light_duration);
    set_prop_alpha("truckLight1", alpha);
    set_prop_alpha("truckLight2", alpha);
}

static void tick_pulse(fixed_t elapsed)
{
    float alpha;
    fixed_t duration;
    if (!g_pulse_enabled || g_pulse_count == 0)
        return;
    duration = (fixed_t)(g_pulse_duration[g_pulse_index] * (float)FIXED_UNIT + 0.5f);
    if (duration <= 0) duration = FIXED_DEC(1, 2);
    g_pulse_time += elapsed;
    while (g_pulse_time >= duration) {
        g_pulse_time -= duration;
        g_pulse_index = (u8)((g_pulse_index + 1) % g_pulse_count);
        duration = (fixed_t)(g_pulse_duration[g_pulse_index] * (float)FIXED_UNIT + 0.5f);
        if (duration <= 0) duration = FIXED_DEC(1, 2);
    }
    alpha = g_pulse_intensity[g_pulse_index];
    set_prop_alpha("backLightColor", alpha);
    set_prop_alpha("backLightWhite", alpha * 0.55f);
}

void SserafimRuntime_Tick(fixed_t elapsed)
{
    int i;
    if (!g_active)
        return;
    for (i = 0; i < SSERAFIM_EXTRA_COUNT; ++i) {
        if (g_extra[i].loaded)
            Character_Tick(&g_extra[i].character);
    }
    tick_dark(elapsed);
    tick_lights(elapsed);
    tick_pulse(elapsed);
    if (g_flash_time > 0) {
        g_flash_time -= elapsed;
        if (g_flash_time < 0) g_flash_time = 0;
    }
}

void SserafimRuntime_Beat(s32 beat)
{
    int i;
    (void)beat;
    if (!g_active)
        return;
    for (i = 0; i < SSERAFIM_EXTRA_COUNT; ++i) {
        Character *character = &g_extra[i].character;
        const char *name;
        if (!g_extra[i].loaded || !g_extra[i].visible)
            continue;
        name = Character_CurrentAnimationName(character);
        if (name == NULL || strncmp(name, "sing", 4) != 0 ||
            Character_AnimationFinished(character))
            Character_Dance(character, true);
    }
}

static u64 character_tint(void)
{
    float brightness = 1.0f - g_dark_amount;
    u8 channel;
    if (brightness < 0.0f) brightness = 0.0f;
    if (brightness > 1.0f) brightness = 1.0f;
    channel = (u8)(128.0f * brightness + 0.5f);
    return GS_SETREG_RGBAQ(channel, channel, channel, 0x80, 0);
}

void SserafimRuntime_DrawRange(
    GSGLOBAL *gs,
    const StageCamera *camera,
    s32 z_min,
    s32 z_max)
{
    int i;
    float zoom;
    float world_scale;
    u64 tint;
    if (!g_active || gs == NULL || SSERAFIM_EXTRA_Z < z_min || SSERAFIM_EXTRA_Z >= z_max)
        return;
    zoom = camera != NULL ? camera->zoom : 1.0f;
    if (zoom <= 0.0f) zoom = 1.0f;
    world_scale = 0.5f * zoom;
    tint = character_tint();

    for (i = 0; i < SSERAFIM_EXTRA_COUNT; ++i) {
        SserafimExtra *extra = &g_extra[i];
        float authored_x;
        float authored_y;
        float x;
        float y;
        if (!extra->loaded || !extra->visible)
            continue;

        authored_x = extra->target_x - extra->character.global_x;
        authored_y = extra->target_y - extra->character.global_y;
        x = (authored_x -
            ((camera != NULL ? camera->scroll_x : 0.0f) * extra->scroll_x)) * world_scale;
        y = (authored_y -
            ((camera != NULL ? camera->scroll_y : 0.0f) * extra->scroll_y)) * world_scale;
        Character_Draw(gs, &extra->character, x, y, world_scale, 2, tint);
    }
}

static void play_lane(Character *character, u8 lane)
{
    static const char *const names[4] = {
        "singLEFT", "singDOWN", "singUP", "singRIGHT"
    };
    if (character == NULL || !character->loaded)
        return;
    Character_Play(character, names[lane & 3], true);
}

static void play_mask(Character *character, u8 mask)
{
    u8 lane;
    for (lane = 0; lane < 4; ++lane) {
        if (mask & (1u << lane))
            play_lane(character, lane);
    }
}

void SserafimRuntime_PlayHitAnimations(
    const GameplayState *game,
    Character *player,
    Character *opponent,
    Character *girlfriend)
{
    u8 player_mask;
    u8 opponent_mask;
    if (!g_active || game == NULL)
        return;
    player_mask = game->events.player_hit_mask;
    opponent_mask = game->events.opponent_hit_mask;

#define ROUTE_CHARACTER(index, character_ptr) do { \
    if ((character_ptr) != NULL) { \
        if (g_singing[(index)]) play_mask((character_ptr), player_mask); \
        else play_mask((character_ptr), opponent_mask); \
    } \
} while (0)

    ROUTE_CHARACTER(0, &g_extra[0].character);
    ROUTE_CHARACTER(1, opponent);
    ROUTE_CHARACTER(2, &g_extra[1].character);
    ROUTE_CHARACTER(3, &g_extra[2].character);
    ROUTE_CHARACTER(4, player);
    ROUTE_CHARACTER(5, girlfriend);
#undef ROUTE_CHARACTER
}

boolean SserafimRuntime_HandleEvent(const char *name, const char *value)
{
    boolean values[SSERAFIM_CAST_COUNT];
    float floats[4];
    int count;
    if (!g_active || name == NULL)
        return false;

    if (strcmp(name, "sserafimShow") == 0) {
        count = json_bool_array(value, "visible", values, 5);
        if (count >= 5) {
            g_visible[0] = values[0];
            g_visible[1] = values[1];
            g_visible[2] = values[2];
            g_visible[3] = values[3];
            g_visible[4] = values[4];
            apply_visibility();
        }
        return true;
    }
    if (strcmp(name, "sserafimSing") == 0) {
        count = json_bool_array(value, "singing", values, SSERAFIM_CAST_COUNT);
        if (count >= 5) {
            int i;
            for (i = 0; i < count && i < SSERAFIM_CAST_COUNT; ++i)
                g_singing[i] = values[i];
        }
        return true;
    }
    if (strcmp(name, "sserafimCover") == 0) {
        set_prop_alpha("solidCover", json_bool(value, "visible", false) ? 1.0f : 0.0f);
        return true;
    }
    if (strcmp(name, "sserafimDark") == 0) {
        float duration = json_float(value, "duration", 0.0f);
        g_dark_start = g_dark_amount;
        g_dark_target = json_float(value, "amount", 0.0f);
        if (g_dark_target < 0.0f) g_dark_target = 0.0f;
        if (g_dark_target > 1.0f) g_dark_target = 1.0f;
        g_dark_time = 0;
        g_dark_duration = duration > 0.0f
            ? (fixed_t)(duration * (float)FIXED_UNIT + 0.5f) : 0;
        return true;
    }
    if (strcmp(name, "sserafimLights") == 0) {
        float duration = json_float(value, "duration", 0.0f);
        g_light_amount = json_float(value, "amount", 1.0f);
        if (g_light_amount < 0.0f) g_light_amount = 0.0f;
        if (g_light_amount > 1.0f) g_light_amount = 1.0f;
        g_light_time = 0;
        g_light_duration = duration > 0.0f
            ? (fixed_t)(duration * (float)FIXED_UNIT + 0.5f) : FIXED_DEC(1, 10);
        set_prop_alpha("truckLight1", g_light_amount);
        set_prop_alpha("truckLight2", g_light_amount);
        return true;
    }
    if (strcmp(name, "sserafimPulseLights") == 0) {
        g_pulse_enabled = json_bool(value, "enabled", false);
        g_pulse_index = 0;
        g_pulse_time = 0;
        if (!g_pulse_enabled) {
            g_pulse_count = 0;
            set_prop_alpha("backLightColor", 0.0f);
            set_prop_alpha("backLightWhite", 0.0f);
            return true;
        }
        count = json_float_array(value, "intensities", floats, 4);
        if (count <= 0) {
            floats[0] = 0.7f;
            count = 1;
        }
        g_pulse_count = (u8)count;
        memcpy(g_pulse_intensity, floats, (size_t)count * sizeof(float));
        count = json_float_array(value, "durations", floats, 4);
        if (count <= 0) {
            floats[0] = 0.5f;
            count = 1;
        }
        {
            int i;
            for (i = 0; i < g_pulse_count; ++i)
                g_pulse_duration[i] = floats[i < count ? i : count - 1];
        }
        return true;
    }
    if (strcmp(name, "sserafimFlash") == 0) {
        float duration = json_float(value, "duration", 0.2f);
        g_flash_duration = duration > 0.0f
            ? (fixed_t)(duration * (float)FIXED_UNIT + 0.5f) : FIXED_DEC(1, 5);
        g_flash_time = g_flash_duration;
        return true;
    }
    if (strcmp(name, "sserafimKick") == 0) {
        boolean final = json_bool(value, "final", false);
        Character_Play(&g_extra[0].character, final ? "kick2" : "kick1", true);
        if (final)
            set_prop_alpha("truckDoor", 1.0f);
        return true;
    }
    if (strcmp(name, "sserafimEnd") == 0) {
        set_prop_alpha("solidCover", 1.0f);
        return true;
    }
    if (strcmp(name, "sserafimGuitarVibration") == 0)
        return true;

    return false;
}

void SserafimRuntime_DrawOverlay(GSGLOBAL *gs)
{
    u8 alpha;
    float ratio;
    if (!g_active || gs == NULL || g_flash_time <= 0 || g_flash_duration <= 0)
        return;
    ratio = (float)g_flash_time / (float)g_flash_duration;
    if (ratio < 0.0f) ratio = 0.0f;
    if (ratio > 1.0f) ratio = 1.0f;
    alpha = (u8)(128.0f * ratio + 0.5f);
    gsKit_prim_sprite(
        gs, 0.0f, 0.0f, 640.0f, 448.0f, 29,
        GS_SETREG_RGBAQ(0x80, 0x80, 0x80, alpha, 0));
}
