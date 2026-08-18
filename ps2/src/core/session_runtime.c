#include "session_runtime.h"

#include <stdio.h>
#include <string.h>

#define PINS_CATALOG_PATH "\\GAME\\PINS\\PINS.FPIN;1"

static boolean flag_enabled(const FunkinSaveData *save, u32 flag)
{
    return save != NULL && (save->settings_flags & flag) != 0;
}

static void configure_combo(SessionRuntime *session)
{
    u16 threshold;
    if (session == NULL)
        return;
    threshold = session->save.combo_swoosh_threshold;
    if (threshold == 0)
        threshold = 1;
    ComboSystem_Init(&session->combo);
    ComboSystem_Configure(
        &session->combo,
        flag_enabled(&session->save, SAVE_FLAG_COMBO_POPUPS),
        flag_enabled(&session->save, SAVE_FLAG_COMBO_SWOOSH),
        flag_enabled(&session->save, SAVE_FLAG_COMBO_SOUND),
        flag_enabled(&session->save, SAVE_FLAG_COMBO_REVERSE_NUMBERS),
        threshold,
        COMBO_SWOOSH_DEFAULT);
    ComboSystem_ResetSong(&session->combo);
}

static void configure_camera_movement(SessionRuntime *session)
{
    float intensity;
    if (session == NULL)
        return;
    intensity = (float)session->save.camera_movement_intensity;
    CameraMovement_Init(&session->camera_movement);
    CameraMovement_Configure(
        &session->camera_movement,
        flag_enabled(&session->save, SAVE_FLAG_CAMERA_MOVEMENT),
        flag_enabled(&session->save, SAVE_FLAG_CAMERA_ONLY_PLAYER),
        intensity);
}

static void build_completion_id(
    SessionRuntime *session,
    const SongDescriptor *descriptor)
{
    if (session == NULL)
        return;
    session->completion_id[0] = '\0';
    if (descriptor == NULL)
        return;
    snprintf(
        session->completion_id,
        sizeof(session->completion_id),
        "%s|%s|%s",
        descriptor->song_id != NULL ? descriptor->song_id : "",
        descriptor->variation != NULL ? descriptor->variation : "default",
        descriptor->difficulty != NULL ? descriptor->difficulty : "normal");
}

void SessionRuntime_Init(
    SessionRuntime *session,
    const StoryCatalog *story,
    const SongCatalog *songs)
{
    (void)story;
    (void)songs;
    if (session == NULL)
        return;

    memset(session, 0, sizeof(*session));
    SaveData_Defaults(&session->save);
    session->memcard_ready = SaveData_Init();
    SaveData_Load(&session->save);
    SaveData_GetProgression(&session->save, &session->progression);

    Gammod_LoadSave(&session->gammod_config, &session->save);
    Gammod_Init(&session->gammod, &session->gammod_config);
    HealthDrain_Init(
        &session->health_drain,
        (HealthDrainLevel)session->save.health_drain_level);
    EndlessMode_Init(
        &session->endless,
        flag_enabled(&session->save, SAVE_FLAG_ENDLESS_DEFAULT));
    configure_combo(session);
    configure_camera_movement(session);
    NoteKindRuntime_Init(&session->note_kinds);
    Hud_Init(&session->hud);

    session->pins_loaded = PointlessPins_Load(&session->pins, PINS_CATALOG_PATH);
    printf("[PS2] pins catalog=%s\n", session->pins_loaded ? "ok" : "unavailable");
}

void SessionRuntime_Shutdown(SessionRuntime *session)
{
    if (session == NULL)
        return;
    SessionRuntime_Save(session);
    SessionRuntime_EndSong(session);
    if (session->pins_loaded)
        PointlessPins_Free(&session->pins);
    StorySession_Stop(&session->story);
    memset(session, 0, sizeof(*session));
}

boolean SessionRuntime_Save(SessionRuntime *session)
{
    if (session == NULL)
        return false;
    SaveData_SetProgression(&session->save, &session->progression);
    Gammod_StoreSave(&session->gammod_config, &session->save);
    if (!session->memcard_ready)
        return false;
    return SaveData_Write(&session->save);
}

boolean SessionRuntime_StartStory(
    SessionRuntime *session,
    const StoryCatalog *story,
    const SongCatalog *songs,
    u16 level_index,
    StoryDifficulty difficulty,
    SongCatalogEntry *first_song)
{
    if (session == NULL || first_song == NULL)
        return false;
    StorySession_Stop(&session->story);
    if (!Progression_IsLevelUnlocked(
            &session->progression,
            story,
            level_index) ||
        !StorySession_Start(
            &session->story,
            story,
            songs,
            level_index,
            difficulty))
        return false;
    if (!StorySession_CurrentSong(&session->story, first_song)) {
        StorySession_Stop(&session->story);
        return false;
    }
    return true;
}

void SessionRuntime_StopStory(SessionRuntime *session)
{
    if (session == NULL)
        return;
    StorySession_Stop(&session->story);
    session->story_mode = false;
}

boolean SessionRuntime_BeginSong(
    SessionRuntime *session,
    GSGLOBAL *gs,
    GameplayState *game,
    const SongDescriptor *descriptor,
    const SongAssetPaths *paths,
    boolean story_mode,
    boolean endless_continuation)
{
    boolean wanted_endless;
    boolean cinema;
    boolean act_like_opponent;

    if (session == NULL || gs == NULL || game == NULL || !game->loaded ||
        descriptor == NULL || paths == NULL || session->song_active)
        return false;

    session->story_mode = story_mode;
    session->endless_continuation = endless_continuation;
    build_completion_id(session, descriptor);

    Gammod_Init(&session->gammod, &session->gammod_config);
    if (!Gammod_TransformChart(&session->gammod, game)) {
        printf("[PS2] Gammod chart transform failed\n");
        return false;
    }

    if (!endless_continuation)
        Gammod_ApplyStartingHealth(&session->gammod, game);

    HealthDrain_Init(
        &session->health_drain,
        (HealthDrainLevel)session->save.health_drain_level);

    if (!endless_continuation) {
        wanted_endless = flag_enabled(&session->save, SAVE_FLAG_ENDLESS_DEFAULT);
        EndlessMode_Init(&session->endless, wanted_endless);
        EndlessMode_SetSong(
            &session->endless,
            descriptor->song_id,
            descriptor->variation,
            story_mode);
        EndlessMode_OnSongStart(&session->endless);
    }

    configure_combo(session);
    configure_camera_movement(session);

    NoteKindRuntime_Init(&session->note_kinds);
    if (!NoteKindRuntime_LoadForChart(&session->note_kinds, paths->chart))
        printf("[PS2] no note-kind sidecar for %s\n", paths->chart);

    Hud_Init(&session->hud);
    if (!Hud_LoadSong(
            gs,
            &session->hud,
            paths->player_base,
            paths->opponent_base))
        printf("[PS2] HUD icons incomplete; using fallbacks\n");

    cinema = session->gammod_config.autoplay == GAMMOD_AUTOPLAY_CINEMA;
    act_like_opponent =
        session->gammod_config.autoplay != GAMMOD_AUTOPLAY_DISABLED &&
        session->gammod_config.autoplay_act_like_opponent;
    Hud_SetGameplayMode(&session->hud, cinema, act_like_opponent);

    if (endless_continuation)
        EndlessMode_RestoreLoop(&session->endless, game);

    session->song_active = true;
    return true;
}

void SessionRuntime_EndSong(SessionRuntime *session)
{
    if (session == NULL)
        return;

    /* This must be called before Gameplay_Free(): Gammod temporarily replaces
     * ChartView.notes with an EE-RAM transform buffer owned by this runtime. */
    Gammod_FreeChart(&session->gammod);
    NoteKindRuntime_Free(&session->note_kinds);
    Hud_ForgetSong(&session->hud);
    session->song_active = false;
    session->story_mode = false;
    session->endless_continuation = false;
    session->completion_id[0] = '\0';
}

void SessionRuntime_PreparePad(
    SessionRuntime *session,
    const GameplayState *game,
    const Pad *physical,
    Pad *effective)
{
    if (session == NULL) {
        if (effective != NULL) {
            if (physical != NULL)
                *effective = *physical;
            else
                memset(effective, 0, sizeof(*effective));
        }
        return;
    }
    Gammod_PreparePad(&session->gammod, game, physical, effective);
}

static void camera_from_hit_mask(
    CameraMovement *movement,
    u8 mask,
    boolean opponent)
{
    int lane;
    if (movement == NULL)
        return;
    for (lane = 0; lane < 4; ++lane) {
        if (mask & (1u << lane))
            CameraMovement_OnNoteHit(movement, (u8)lane, opponent);
    }
}

void SessionRuntime_AfterGameplayFrame(
    SessionRuntime *session,
    GameplayState *game,
    fixed_t elapsed)
{
    if (session == NULL || game == NULL || !session->song_active)
        return;

    NoteKindRuntime_ResolveFrame(&session->note_kinds, game);
    Gammod_OnGameplayFrame(&session->gammod, game, elapsed);
    HealthDrain_OnFrame(&session->health_drain, game, elapsed);
    EndlessMode_OnGameplayFrame(&session->endless, game);
    ComboSystem_OnGameplayFrame(&session->combo, game);

    camera_from_hit_mask(
        &session->camera_movement,
        game->events.player_hit_mask,
        false);
    camera_from_hit_mask(
        &session->camera_movement,
        game->events.opponent_hit_mask,
        true);
    CameraMovement_Tick(&session->camera_movement);

    if (game->events.just_step && game->song_step >= 0 &&
        (game->song_step & 3) == 0)
        Hud_OnBeat(&session->hud, game->song_step / 4, &session->save);
    Hud_Tick(&session->hud, game, &session->combo, &session->save, elapsed);
}

static void fallback_lane_animation(Character *character, u8 lane)
{
    static const char *names[4] = {
        "singLEFT", "singDOWN", "singUP", "singRIGHT"
    };
    if (character == NULL || !character->loaded)
        return;
    Character_Play(character, names[lane & 3], true);
}

void SessionRuntime_PlayHitAnimations(
    SessionRuntime *session,
    Character *player,
    Character *opponent)
{
    int lane;
    if (session == NULL || !session->song_active)
        return;

    for (lane = 0; lane < 4; ++lane) {
        if (session->note_kinds.player[lane].valid) {
            if (!NoteKindRuntime_PlayLaneAnimation(
                    &session->note_kinds,
                    player,
                    &session->note_kinds.player[lane],
                    true))
                fallback_lane_animation(player, (u8)lane);
        }
        if (session->note_kinds.opponent[lane].valid) {
            if (!NoteKindRuntime_PlayLaneAnimation(
                    &session->note_kinds,
                    opponent,
                    &session->note_kinds.opponent[lane],
                    true))
                fallback_lane_animation(opponent, (u8)lane);
        }
    }
}

void SessionRuntime_OnDeath(SessionRuntime *session)
{
    if (session == NULL)
        return;
    EndlessMode_OnDeath(&session->endless);
}

float SessionRuntime_CameraX(const SessionRuntime *session)
{
    if (session == NULL)
        return 0.0f;
    return CameraMovement_X(&session->camera_movement);
}

float SessionRuntime_CameraY(const SessionRuntime *session)
{
    if (session == NULL)
        return 0.0f;
    return CameraMovement_Y(&session->camera_movement);
}

static PointlessPinsReward award_completion(
    SessionRuntime *session,
    const GameplayState *game,
    boolean endless)
{
    PointlessPinsReward empty;
    u32 judged;
    u32 sicks;

    memset(&empty, 0, sizeof(empty));
    if (session == NULL || game == NULL || !session->pins_loaded ||
        session->completion_id[0] == '\0')
        return empty;

    judged = game->rhythm.judged_notes;
    sicks = game->rhythm.rating_counts[HIT_SICK];
    /* Any gameplay miss disqualifies All Sicks without treating empty presses
     * as chart notes for normal statistics. */
    if (game->misses != 0)
        ++judged;

    return PointlessPins_AwardSong(
        &session->save,
        session->completion_id,
        game->rhythm.score,
        judged,
        sicks,
        endless,
        session->endless.current_loop);
}

SessionCompletion SessionRuntime_CompleteSong(
    SessionRuntime *session,
    GameplayState *game)
{
    SessionCompletion result;
    u16 completed_level = 0;
    boolean was_story;

    memset(&result, 0, sizeof(result));
    result.action = SESSION_COMPLETE_RETURN;
    if (session == NULL || game == NULL)
        return result;

    if (session->endless.enabled && !session->endless.incompatible) {
        EndlessMode_PrepareLoop(&session->endless, game);
        session->endless_continuation = true;
        result.action = SESSION_COMPLETE_ENDLESS_LOOP;
        return result;
    }

    result.reward = award_completion(session, game, false);

    was_story = session->story.active;
    if (was_story)
        completed_level = session->story.level_index;

    if (was_story && StorySession_Advance(&session->story)) {
        if (StorySession_CurrentSong(&session->story, &result.next_song)) {
            result.action = SESSION_COMPLETE_STORY_NEXT;
            SessionRuntime_Save(session);
            return result;
        }
        StorySession_Stop(&session->story);
    }

    if (was_story) {
        result.story_level_cleared = Progression_CompleteLevel(
            &session->progression,
            session->story.story != NULL ? session->story.story : NULL,
            completed_level);
        /* StorySession_Advance clears the session at the end of a level, so
         * Progression_CompleteLevel needs the catalog that was cached before
         * the clear. If the pointer was cleared, directly set the validated bit. */
        if (!result.story_level_cleared && completed_level < PROGRESSION_MAX_STORY_LEVELS) {
            session->progression.completed_story_levels |= (1ull << completed_level);
            result.story_level_cleared = true;
        }
    }

    SessionRuntime_Save(session);
    return result;
}

PointlessPinsReward SessionRuntime_EndEndless(
    SessionRuntime *session,
    const GameplayState *game)
{
    PointlessPinsReward result = award_completion(session, game, true);
    if (session != NULL) {
        session->endless.enabled = false;
        session->endless.ending = true;
        SessionRuntime_Save(session);
    }
    return result;
}
