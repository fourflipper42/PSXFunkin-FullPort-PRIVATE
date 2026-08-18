#ifndef FNF_PS2_GAMMOD_H
#define FNF_PS2_GAMMOD_H

#include "gameplay.h"
#include "save_data.h"

typedef enum GammodAutoPlay {
    GAMMOD_AUTOPLAY_DISABLED = 0,
    GAMMOD_AUTOPLAY_AUTO,
    GAMMOD_AUTOPLAY_CINEMA
} GammodAutoPlay;

typedef enum GammodLongNotes {
    GAMMOD_LONG_NORMAL = 0,
    GAMMOD_LONG_NONE,
    GAMMOD_LONG_ALL,
    GAMMOD_LONG_INVERTED
} GammodLongNotes;

typedef enum GammodNotePlacement {
    GAMMOD_PLACEMENT_NORMAL = 0,
    GAMMOD_PLACEMENT_MIRROR,
    GAMMOD_PLACEMENT_RANDOM
} GammodNotePlacement;

typedef enum GammodPerfectOnly {
    GAMMOD_PERFECT_DISABLED = 0,
    GAMMOD_PERFECT_PURPLE,
    GAMMOD_PERFECT_GOLDEN
} GammodPerfectOnly;

typedef enum GammodPlayerSide {
    GAMMOD_SIDE_NORMAL = 0,
    GAMMOD_SIDE_OPPOSITE,
    GAMMOD_SIDE_BOTH
} GammodPlayerSide;

typedef enum GammodSkipSilence {
    GAMMOD_SKIP_SILENCE_DISABLED = 0,
    GAMMOD_SKIP_SILENCE_INTRO
} GammodSkipSilence;

typedef struct GammodConfig {
    GammodAutoPlay autoplay;
    GammodLongNotes long_notes;
    GammodNotePlacement note_placement;
    GammodPerfectOnly perfect_only;
    GammodPlayerSide player_side;
    GammodSkipSilence skip_silence;

    boolean extra_notes;
    boolean ghost_tapping;
    boolean scroll_velocities;
    boolean custom_judgements;
    boolean reset_on_death;
    boolean skip_countdown;
    boolean random_avoid_jacks;
    boolean perfect_fail_on_ghost;
    boolean autoplay_act_like_opponent;
    boolean playback_stage_rate;
    boolean playback_match_event_durations;
    boolean playback_match_scroll_speed;

    float custom_scroll_speed;
    float health_drain;
    float health_gain;
    float health_loss;
    float playback_rate;
    u16 starting_health_percent;
    u16 sick_window_ms;
    u16 good_window_ms;
    u16 bad_window_ms;
    u16 shit_window_ms;
    u8 skip_safety_beats;
    boolean skip_count_enemy_notes;
} GammodConfig;

typedef struct GammodRuntime {
    GammodConfig config;
    Note *transformed_notes;
    size_t transformed_count;
    boolean transformed;
    boolean perfect_failed;
} GammodRuntime;

void Gammod_Defaults(GammodConfig *config);
void Gammod_LoadSave(GammodConfig *config, const FunkinSaveData *save);
void Gammod_StoreSave(const GammodConfig *config, FunkinSaveData *save);
void Gammod_Init(GammodRuntime *runtime, const GammodConfig *config);
void Gammod_FreeChart(GammodRuntime *runtime);
boolean Gammod_TransformChart(GammodRuntime *runtime, GameplayState *game);
void Gammod_ApplyStartingHealth(GammodRuntime *runtime, GameplayState *game);
void Gammod_PreparePad(
    GammodRuntime *runtime,
    const GameplayState *game,
    const Pad *physical,
    Pad *effective);
void Gammod_OnGameplayFrame(GammodRuntime *runtime, GameplayState *game, fixed_t elapsed);
boolean Gammod_ShouldSkipCountdown(const GammodRuntime *runtime);
boolean Gammod_ResetOnDeath(const GammodRuntime *runtime);
boolean Gammod_PerfectFailed(const GammodRuntime *runtime);

#endif
