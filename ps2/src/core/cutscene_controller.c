#include "cutscene_controller.h"

#include <ctype.h>
#include <stdio.h>
#include <string.h>

#define CUTSCENE_MAP_PATH "\\GAME\\CUTSCENE\\CUTMAP.FCMP;1"

static CutsceneMap g_map;
static CutsceneStream g_stream;
static GSGLOBAL *g_gs;
static boolean g_map_loaded;
static boolean g_active;
static boolean g_open_pending;
static boolean g_post_pending;
static char g_pending_base[256];
static char g_post_base[256];
static char g_last_story_song[96];

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

static void close_active(void)
{
    if (g_stream.loaded)
        CutsceneStream_Close(&g_stream);
    g_active = false;
    g_open_pending = false;
    g_pending_base[0] = '\0';
}

static void clear_story_state(void)
{
    close_active();
    g_post_pending = false;
    g_post_base[0] = '\0';
    g_last_story_song[0] = '\0';
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

    close_active();
    if (!g_map_loaded || gs == NULL || song_id == NULL || !story_mode) {
        g_post_pending = false;
        g_post_base[0] = '\0';
        return false;
    }

    same_story_song = strcmp(g_last_story_song, song_id) == 0;
    g_gs = gs;

    /* Retrying the same Story song must not replay its intro. Keep any armed
     * ending movie, though, because the retry still has to earn that ending. */
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
    g_active = true;
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
    g_active = true;
    printf("[PS2] Story ending cutscene queued\n");
    return true;
}

void CutsceneController_HandlePad(const Pad *pad)
{
    if (!g_active || pad == NULL)
        return;

    if (pad->press & PAD_CROSS) {
        printf("[PS2] cutscene skipped\n");
        close_active();
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
            close_active();
            return;
        }
    }

    CutsceneStream_Tick(g_gs, &g_stream);
    if (CutsceneStream_Finished(&g_stream)) {
        printf("[PS2] cutscene finished\n");
        close_active();
    }
}

void CutsceneController_Draw(GSGLOBAL *gs)
{
    const u64 white = GS_SETREG_RGBAQ(0x80, 0x80, 0x80, 0x80, 0);
    if (!g_active || g_open_pending || gs == NULL)
        return;
    CutsceneStream_Draw(gs, &g_stream, 30, white);
}

boolean CutsceneController_Active(void)
{
    return g_active;
}
