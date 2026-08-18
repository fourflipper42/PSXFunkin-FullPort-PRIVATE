#include "cutscene_controller.h"

#include "presentation_registry.h"
#include "timer.h"
#include <stdio.h>
#include <string.h>

#define CUTSCENE_MAP_PATH "\\GAME\\CUTSCENE\\CUTMAP.FCMP;1"

typedef enum NativeCutsceneKind {
    NATIVE_CUTSCENE_NONE = 0,
    NATIVE_CUTSCENE_DARNELL_INTRO,
    NATIVE_CUTSCENE_2HOT_OUTRO
} NativeCutsceneKind;

static CutsceneMap g_map;
static CutsceneStream g_stream;
static GSGLOBAL *g_gs;
static boolean g_map_loaded;
static boolean g_active;
static boolean g_open_pending;
static boolean g_video_visible;
static boolean g_post_pending;
static boolean g_start_darnell_after_video;
static char g_pending_base[256];
static char g_post_base[256];
static char g_last_story_song[96];

static NativeCutsceneKind g_native_kind;
static fixed_t g_native_time;
static fixed_t g_native_previous;
static float g_camera_x;
static float g_camera_y;
static float g_camera_start_x;
static float g_camera_start_y;
static float g_camera_target_x;
static float g_camera_target_y;
static fixed_t g_camera_tween_time;
static fixed_t g_camera_tween_duration;

static void uppercase_ascii(char *text)
{
    unsigned char *p = (unsigned char *)text;
    if (text == NULL)
        return;
    while (*p != 0) {
        if (*p >= 'a' && *p <= 'z')
            *p = (unsigned char)(*p - 'a' + 'A');
        ++p;
    }
}

static fixed_t seconds_fixed(float seconds)
{
    return (fixed_t)(seconds * (float)FIXED_UNIT + 0.5f);
}

static boolean crossed(float seconds)
{
    fixed_t point = seconds_fixed(seconds);
    return g_native_previous < point && g_native_time >= point;
}

static void make_base(char *out, size_t out_size, const char *cutscene_id)
{
    char id[128];
    if (out == NULL || out_size == 0)
        return;
    out[0] = '\0';
    if (cutscene_id == NULL || cutscene_id[0] == '\0')
        return;
    strncpy(id, cutscene_id, sizeof(id) - 1);
    id[sizeof(id) - 1] = '\0';
    uppercase_ascii(id);
    snprintf(out, out_size, "\\GAME\\CUTSCENE\\%s", id);
}

static void stop_video(void)
{
    if (g_stream.loaded)
        CutsceneStream_Close(&g_stream);
    g_open_pending = false;
    g_pending_base[0] = '\0';
    g_video_visible = false;
}

static void reset_native(void)
{
    g_native_kind = NATIVE_CUTSCENE_NONE;
    g_native_time = 0;
    g_native_previous = 0;
    g_camera_x = 0.0f;
    g_camera_y = 0.0f;
    g_camera_start_x = 0.0f;
    g_camera_start_y = 0.0f;
    g_camera_target_x = 0.0f;
    g_camera_target_y = 0.0f;
    g_camera_tween_time = 0;
    g_camera_tween_duration = 0;
}

static void finish_active(void)
{
    stop_video();
    g_active = false;
    g_start_darnell_after_video = false;
    reset_native();
}

static void clear_story_state(void)
{
    finish_active();
    g_post_pending = false;
    g_post_base[0] = '\0';
    g_last_story_song[0] = '\0';
}

static float focus_x(const StageCharacterSlot *slot)
{
    return slot != NULL ? slot->x + slot->camera_x : 0.0f;
}

static float focus_y(const StageCharacterSlot *slot)
{
    return slot != NULL ? slot->y + slot->camera_y : 0.0f;
}

static void camera_to_absolute(float x, float y, float duration)
{
    Stage *stage = PresentationRegistry_Stage();
    const StageCharacterSlot *player = Stage_PlayerSlot(stage);
    float base_x = focus_x(player);
    float base_y = focus_y(player);

    g_camera_start_x = g_camera_x;
    g_camera_start_y = g_camera_y;
    g_camera_target_x = x - base_x;
    g_camera_target_y = y - base_y;
    g_camera_tween_time = 0;
    g_camera_tween_duration = duration > 0.0f ? seconds_fixed(duration) : 0;
    if (g_camera_tween_duration == 0) {
        g_camera_x = g_camera_target_x;
        g_camera_y = g_camera_target_y;
    }
}

static void camera_to_slot(const StageCharacterSlot *slot, float add_x, float add_y, float duration)
{
    camera_to_absolute(focus_x(slot) + add_x, focus_y(slot) + add_y, duration);
}

static void tick_camera_tween(fixed_t elapsed)
{
    float t;
    if (g_camera_tween_duration <= 0)
        return;
    g_camera_tween_time += elapsed;
    if (g_camera_tween_time >= g_camera_tween_duration) {
        g_camera_tween_time = g_camera_tween_duration;
        g_camera_x = g_camera_target_x;
        g_camera_y = g_camera_target_y;
        g_camera_tween_duration = 0;
        return;
    }
    t = (float)g_camera_tween_time / (float)g_camera_tween_duration;
    /* Smoothstep is a close, cheap stand-in for the mostly quad/sine source tweens. */
    t = t * t * (3.0f - 2.0f * t);
    g_camera_x = g_camera_start_x + (g_camera_target_x - g_camera_start_x) * t;
    g_camera_y = g_camera_start_y + (g_camera_target_y - g_camera_start_y) * t;
}

static void start_darnell_native(void)
{
    Character *player = PresentationRegistry_Player();
    Stage *stage = PresentationRegistry_Stage();
    const StageCharacterSlot *player_slot = Stage_PlayerSlot(stage);

    reset_native();
    g_native_kind = NATIVE_CUTSCENE_DARNELL_INTRO;
    g_active = true;
    if (player != NULL)
        Character_Play(player, "intro1", true);
    camera_to_slot(player_slot, 250.0f, 0.0f, 0.0f);
    printf("[PS2] native Darnell intro started\n");
}

static void start_2hot_native(void)
{
    Character *girlfriend = PresentationRegistry_Girlfriend();
    reset_native();
    g_native_kind = NATIVE_CUTSCENE_2HOT_OUTRO;
    g_active = true;
    g_video_visible = false;
    if (girlfriend != NULL)
        Character_Dance(girlfriend, true);
    printf("[PS2] native 2hot outro started\n");
}

static void tick_darnell_native(fixed_t elapsed)
{
    Stage *stage = PresentationRegistry_Stage();
    Character *player = PresentationRegistry_Player();
    Character *opponent = PresentationRegistry_Opponent();
    Character *girlfriend = PresentationRegistry_Girlfriend();
    const StageCharacterSlot *dad = Stage_OpponentSlot(stage);

    g_native_previous = g_native_time;
    g_native_time += elapsed;
    tick_camera_tween(elapsed);

    if (crossed(2.0f))
        camera_to_slot(dad, 100.0f, 0.0f, 2.5f);
    if (crossed(5.0f) && opponent != NULL)
        Character_Play(opponent, "lightCan", true);
    if (crossed(6.0f)) {
        if (player != NULL)
            Character_Play(player, "cock", true);
        camera_to_slot(dad, 180.0f, 0.0f, 0.4f);
    }
    if (crossed(6.4f) && opponent != NULL)
        Character_Play(opponent, "kickCan", true);
    if (crossed(6.9f) && opponent != NULL)
        Character_Play(opponent, "kneeCan", true);
    if (crossed(7.1f)) {
        if (player != NULL)
            Character_Play(player, "intro2", true);
        camera_to_slot(dad, 100.0f, 0.0f, 1.0f);
    }
    if (crossed(7.9f) && opponent != NULL)
        Character_Play(opponent, "laughCutscene", true);
    if (crossed(8.2f) && girlfriend != NULL)
        Character_Play(girlfriend, "laughCutscene", true);
    if (crossed(10.0f)) {
        camera_to_slot(dad, 180.0f, 0.0f, 0.0f);
        g_active = false;
        g_native_kind = NATIVE_CUTSCENE_NONE;
        printf("[PS2] native Darnell intro finished\n");
    }
}

static void tick_2hot_native(fixed_t elapsed)
{
    Character *player = PresentationRegistry_Player();
    Character *opponent = PresentationRegistry_Opponent();

    g_native_previous = g_native_time;
    g_native_time += elapsed;
    tick_camera_tween(elapsed);

    if (crossed(1.0f))
        camera_to_absolute(1539.0f, 833.5f, 2.0f);
    if (crossed(2.0f) && player != NULL)
        Character_Play(player, "intro1", true);
    if (crossed(2.5f) && opponent != NULL)
        Character_Play(opponent, "pissed", true);
    if (crossed(6.0f)) {
        g_video_visible = true;
        g_native_kind = NATIVE_CUTSCENE_NONE;
        g_camera_x = 0.0f;
        g_camera_y = 0.0f;
        printf("[PS2] 2hot ending video revealed\n");
    }
}

boolean CutsceneController_Init(void)
{
    memset(&g_map, 0, sizeof(g_map));
    memset(&g_stream, 0, sizeof(g_stream));
    g_gs = NULL;
    g_map_loaded = false;
    clear_story_state();
    g_map_loaded = CutsceneMap_Load(&g_map, CUTSCENE_MAP_PATH);
    printf("[PS2] cutscene map=%s entries=%u\n",
        g_map_loaded ? "ok" : "unavailable",
        g_map_loaded ? (unsigned)g_map.count : 0u);
    return g_map_loaded;
}

void CutsceneController_Shutdown(void)
{
    clear_story_state();
    if (g_map_loaded)
        CutsceneMap_Free(&g_map);
    memset(&g_map, 0, sizeof(g_map));
    g_map_loaded = false;
    g_gs = NULL;
}

void CutsceneController_ResetStory(void)
{
    clear_story_state();
}

boolean CutsceneController_BeginSong(
    GSGLOBAL *gs,
    const char *song_id,
    boolean story_mode)
{
    const char *pre_id = NULL;
    const char *post_id = NULL;
    boolean same_story_song;

    stop_video();
    reset_native();
    g_active = false;
    g_start_darnell_after_video = false;
    if (!g_map_loaded || gs == NULL || song_id == NULL || !story_mode) {
        g_post_pending = false;
        g_post_base[0] = '\0';
        return false;
    }

    same_story_song = strcmp(g_last_story_song, song_id) == 0;
    g_gs = gs;
    if (same_story_song)
        return false;

    strncpy(g_last_story_song, song_id, sizeof(g_last_story_song) - 1);
    g_last_story_song[sizeof(g_last_story_song) - 1] = '\0';

    g_post_pending = false;
    g_post_base[0] = '\0';
    if (CutsceneMap_FindPostSong(&g_map, song_id, true, &post_id) &&
        post_id != NULL && post_id[0] != '\0') {
        make_base(g_post_base, sizeof(g_post_base), post_id);
        g_post_pending = g_post_base[0] != '\0';
        if (g_post_pending)
            printf("[PS2] Story ending cutscene armed: %s -> %s\n", song_id, post_id);
    }

    if (!CutsceneMap_FindPreSong(&g_map, song_id, true, &pre_id) ||
        pre_id == NULL || pre_id[0] == '\0')
        return false;

    make_base(g_pending_base, sizeof(g_pending_base), pre_id);
    if (g_pending_base[0] == '\0')
        return false;
    g_open_pending = true;
    g_video_visible = true;
    g_active = true;
    g_start_darnell_after_video = strcmp(song_id, "darnell") == 0;
    printf("[PS2] Story intro cutscene queued: %s -> %s\n", song_id, pre_id);
    return true;
}

boolean CutsceneController_BeginPostSong(void)
{
    if (g_active || !g_post_pending || g_gs == NULL || g_post_base[0] == '\0')
        return false;
    strncpy(g_pending_base, g_post_base, sizeof(g_pending_base) - 1);
    g_pending_base[sizeof(g_pending_base) - 1] = '\0';
    g_post_pending = false;
    g_post_base[0] = '\0';
    g_open_pending = true;
    g_video_visible = true;
    g_active = true;
    if (strcmp(g_last_story_song, "2hot") == 0)
        start_2hot_native();
    printf("[PS2] Story ending cutscene queued\n");
    return true;
}

void CutsceneController_HandlePad(const Pad *pad)
{
    if (!g_active || pad == NULL)
        return;
    if (pad->press & PAD_CROSS) {
        printf("[PS2] cutscene skipped\n");
        finish_active();
    }
}

void CutsceneController_Tick(void)
{
    if (!g_active || g_gs == NULL)
        return;

    if (g_open_pending) {
        g_open_pending = false;
        if (!CutsceneStream_Open(g_gs, &g_stream, g_pending_base)) {
            printf("[PS2] cutscene open failed: %s\n", g_pending_base);
            finish_active();
            return;
        }
    }

    if (g_stream.loaded)
        CutsceneStream_Tick(g_gs, &g_stream);

    if (g_native_kind == NATIVE_CUTSCENE_DARNELL_INTRO)
        tick_darnell_native(timer_dt);
    else if (g_native_kind == NATIVE_CUTSCENE_2HOT_OUTRO)
        tick_2hot_native(timer_dt);

    if (g_stream.loaded && CutsceneStream_Finished(&g_stream)) {
        if (g_start_darnell_after_video) {
            g_start_darnell_after_video = false;
            stop_video();
            start_darnell_native();
            return;
        }
        finish_active();
        printf("[PS2] cutscene finished\n");
    }
}

void CutsceneController_Draw(GSGLOBAL *gs)
{
    const u64 white = GS_SETREG_RGBAQ(0x80, 0x80, 0x80, 0x80, 0);
    if (!g_active || !g_video_visible || g_open_pending || !g_stream.loaded || gs == NULL)
        return;
    CutsceneStream_Draw(gs, &g_stream, 30, white);
}

boolean CutsceneController_Active(void)
{
    return g_active;
}

float CutsceneController_CameraX(void)
{
    return g_camera_x;
}

float CutsceneController_CameraY(void)
{
    return g_camera_y;
}
