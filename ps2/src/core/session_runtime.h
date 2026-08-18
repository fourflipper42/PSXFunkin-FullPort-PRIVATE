#ifndef FNF_PS2_SESSION_RUNTIME_H
#define FNF_PS2_SESSION_RUNTIME_H

#include "camera_movement.h"
#include "combo_system.h"
#include "endless_mode.h"
#include "gammod.h"
#include "health_drain.h"
#include "hud.h"
#include "note_kind_runtime.h"
#include "pointless_pins.h"
#include "progression.h"
#include "save_data.h"
#include "song_catalog.h"
#include "song_descriptor.h"
#include "story_catalog.h"
#include "story_session.h"

typedef enum SessionCompletionAction {
    SESSION_COMPLETE_RETURN = 0,
    SESSION_COMPLETE_ENDLESS_LOOP,
    SESSION_COMPLETE_STORY_NEXT
} SessionCompletionAction;

typedef struct SessionCompletion {
    SessionCompletionAction action;
    SongCatalogEntry next_song;
    PointlessPinsReward reward;
    boolean story_level_cleared;
} SessionCompletion;

typedef struct SessionRuntime {
    FunkinSaveData save;
    ProgressionState progression;
    StorySession story;
    PointlessPinsCatalog pins;

    GammodConfig gammod_config;
    GammodRuntime gammod;
    HealthDrain health_drain;
    EndlessMode endless;
    ComboSystem combo;
    CameraMovement camera_movement;
    NoteKindRuntime note_kinds;
    HudRuntime hud;

    boolean memcard_ready;
    boolean pins_loaded;
    boolean song_active;
    boolean story_mode;
    boolean endless_continuation;
    char completion_id[256];
} SessionRuntime;

void SessionRuntime_Init(
    SessionRuntime *session,
    const StoryCatalog *story,
    const SongCatalog *songs);
void SessionRuntime_Shutdown(SessionRuntime *session);
boolean SessionRuntime_Save(SessionRuntime *session);

boolean SessionRuntime_StartStory(
    SessionRuntime *session,
    const StoryCatalog *story,
    const SongCatalog *songs,
    u16 level_index,
    StoryDifficulty difficulty,
    SongCatalogEntry *first_song);
void SessionRuntime_StopStory(SessionRuntime *session);

boolean SessionRuntime_BeginSong(
    SessionRuntime *session,
    GSGLOBAL *gs,
    GameplayState *game,
    const SongDescriptor *descriptor,
    const SongAssetPaths *paths,
    boolean story_mode,
    boolean endless_continuation);
void SessionRuntime_EndSong(SessionRuntime *session);

void SessionRuntime_PreparePad(
    SessionRuntime *session,
    const GameplayState *game,
    const Pad *physical,
    Pad *effective);
void SessionRuntime_AfterGameplayFrame(
    SessionRuntime *session,
    GameplayState *game,
    fixed_t elapsed);
void SessionRuntime_PlayHitAnimations(
    SessionRuntime *session,
    Character *player,
    Character *opponent);
void SessionRuntime_OnDeath(SessionRuntime *session);

float SessionRuntime_CameraX(const SessionRuntime *session);
float SessionRuntime_CameraY(const SessionRuntime *session);

SessionCompletion SessionRuntime_CompleteSong(
    SessionRuntime *session,
    GameplayState *game);
PointlessPinsReward SessionRuntime_EndEndless(
    SessionRuntime *session,
    const GameplayState *game);

#endif
