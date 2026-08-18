#define SESSION_RUNTIME_IMPLEMENTATION
#include "session_runtime.h"

#include "cutscene_controller.h"
#include <string.h>

void SessionRuntime_InitCutsceneAware(
    SessionRuntime *session,
    const StoryCatalog *story,
    const SongCatalog *songs)
{
    SessionRuntime_Init(session, story, songs);
    CutsceneController_Init();
}

void SessionRuntime_ShutdownCutsceneAware(SessionRuntime *session)
{
    CutsceneController_Shutdown();
    SessionRuntime_Shutdown(session);
}

boolean SessionRuntime_StartStoryCutsceneAware(
    SessionRuntime *session,
    const StoryCatalog *story,
    const SongCatalog *songs,
    u16 level_index,
    StoryDifficulty difficulty,
    SongCatalogEntry *first_song)
{
    boolean result;
    CutsceneController_ResetStory();
    result = SessionRuntime_StartStory(
        session, story, songs, level_index, difficulty, first_song);
    if (!result)
        CutsceneController_ResetStory();
    return result;
}

void SessionRuntime_StopStoryCutsceneAware(SessionRuntime *session)
{
    CutsceneController_ResetStory();
    SessionRuntime_StopStory(session);
}

boolean SessionRuntime_BeginSongCutsceneAware(
    SessionRuntime *session,
    GSGLOBAL *gs,
    GameplayState *game,
    const SongDescriptor *descriptor,
    const SongAssetPaths *paths,
    boolean story_mode,
    boolean endless_continuation)
{
    boolean result = SessionRuntime_BeginSong(
        session,
        gs,
        game,
        descriptor,
        paths,
        story_mode,
        endless_continuation);
    if (!result)
        return false;

    if (!endless_continuation && descriptor != NULL && descriptor->song_id != NULL)
        CutsceneController_BeginSong(gs, descriptor->song_id, story_mode);
    return true;
}

void SessionRuntime_PreparePadCutsceneAware(
    SessionRuntime *session,
    const GameplayState *game,
    const Pad *physical,
    Pad *effective)
{
    if (CutsceneController_Active()) {
        CutsceneController_HandlePad(physical);
        if (CutsceneController_Active()) {
            if (effective != NULL)
                memset(effective, 0, sizeof(*effective));
            return;
        }
    }
    SessionRuntime_PreparePad(session, game, physical, effective);
}
