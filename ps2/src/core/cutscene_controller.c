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

static void close_active(void)
{
    if (g_active || g_stream.loaded)
        CutsceneStream_Close(&g_stream);
    g_active = false;
}

boolean CutsceneController_Init(void)
{
    memset(&g_map, 0, sizeof(g_map));
    memset(&g_stream, 0, sizeof(g_stream));
    g_gs = NULL;
    g_active = false;
    g_last_story_song[0] = '\0';
    g_map_loaded = CutsceneMap_Load(&g_map, CUTSCENE_MAP_PATH);
    printf("[PS2] cutscene map=%s entries=%u\n",
        g_map_loaded ? "ok" : "unavailable",
        g_map_loaded ? (unsigned)g_map.count : 0u);
    return g_map_loaded;
}

void CutsceneController_Shutdown(void)
{
    close_active();
    if (g_map_loaded)
        CutsceneMap_Free(&g_map);
    memset(&g_map, 0, sizeof(g_map));
    g_map_loaded = false;
    g_gs = NULL;
    g_last_story_song[0] = '\0';
}

void CutsceneController_ResetStory(void)
{
    close_active();
    g_last_story_song[0] = '\0';
}

boolean CutsceneController_BeginSong(
    GSGLOBAL *gs,
    const char *song_id,
    boolean story_mode)
{
    const char *cutscene_id;
    char id[128];
    char base[256];

    close_active();
    if (!g_map_loaded || gs == NULL || song_id == NULL || !story_mode)
        return false;

    /* A retry rebuilds the song runtime but stays in the same Story session.
     * Preserve the most recently attempted Story song so its intro video does
     * not replay until the player leaves/restarts Story Mode. */
    if (strcmp(g_last_story_song, song_id) == 0)
        return false;

    if (!CutsceneMap_FindPreSong(&g_map, song_id, true, &cutscene_id) ||
        cutscene_id == NULL || cutscene_id[0] == '\0')
        return false;

    strncpy(id, cutscene_id, sizeof(id) - 1);
    id[sizeof(id) - 1] = '\0';
    uppercase_ascii(id);
    snprintf(base, sizeof(base), "\\GAME\\CUTSCENE\\%s", id);

    if (!CutsceneStream_Open(gs, &g_stream, base)) {
        printf("[PS2] cutscene unavailable for %s: %s\n", song_id, base);
        return false;
    }

    strncpy(g_last_story_song, song_id, sizeof(g_last_story_song) - 1);
    g_last_story_song[sizeof(g_last_story_song) - 1] = '\0';
    g_gs = gs;
    g_active = true;
    printf("[PS2] Story cutscene: %s -> %s\n", song_id, cutscene_id);
    return true;
}

void CutsceneController_HandlePad(const Pad *pad)
{
    if (!g_active || pad == NULL)
        return;

    /* CROSS is the PS2-native cutscene skip. START is deliberately left to
     * the normal gameplay pause path so the two states never fight over it. */
    if (pad->press & PAD_CROSS) {
        printf("[PS2] cutscene skipped\n");
        close_active();
    }
}

void CutsceneController_Tick(void)
{
    if (!g_active || g_gs == NULL)
        return;
    CutsceneStream_Tick(g_gs, &g_stream);
    if (CutsceneStream_Finished(&g_stream)) {
        printf("[PS2] cutscene finished\n");
        close_active();
    }
}

void CutsceneController_Draw(GSGLOBAL *gs)
{
    const u64 white = GS_SETREG_RGBAQ(0x80, 0x80, 0x80, 0x80, 0);
    if (!g_active || gs == NULL)
        return;
    CutsceneStream_Draw(gs, &g_stream, 30, white);
}

boolean CutsceneController_Active(void)
{
    return g_active;
}
