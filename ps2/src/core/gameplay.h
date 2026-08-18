#ifndef FNF_PS2_GAMEPLAY_H
#define FNF_PS2_GAMEPLAY_H

#include "chart_asset.h"
#include "pad.h"
#include "rhythm.h"
#include "song_events.h"
#include "song_stream.h"

#define INPUT_LEFT  (PAD_LEFT  | PAD_SQUARE)
#define INPUT_DOWN  (PAD_DOWN  | PAD_CROSS)
#define INPUT_UP    (PAD_UP    | PAD_TRIANGLE)
#define INPUT_RIGHT (PAD_RIGHT | PAD_CIRCLE)
#define GAMEPLAY_FRAME_SONG_EVENT_MAX 16

typedef struct GameplaySongEventFrame {
    u16 kind;
    const char *name;
    const char *value;
} GameplaySongEventFrame;

typedef struct GameplayFrameEvents {
    u8 player_hit_mask;
    u8 opponent_hit_mask;
    boolean player_missed;
    boolean mine_hit;
    boolean just_step;
    boolean song_event_fired;
    boolean song_event_overflow;
    boolean camera_focus_changed;
    boolean player_died;
    boolean song_finished;
    u8 camera_focus;
    u8 song_event_count;
    u16 last_song_event_kind;
    const char *last_song_event_name;
    const char *last_song_event_value;
    GameplaySongEventFrame song_events[GAMEPLAY_FRAME_SONG_EVENT_MAX];
    HitRating last_rating;
} GameplayFrameEvents;

typedef struct GameplayScrollTween {
    fixed_t start_player;
    fixed_t start_opponent;
    fixed_t target_player;
    fixed_t target_opponent;
    fixed_t elapsed;
    fixed_t duration;
    u8 side_mask;
    u8 ease_type;
    u8 ease_dir;
    boolean active;
} GameplayScrollTween;

typedef struct GameplayState {
    ChartAsset chart;
    SongEventStream song_events;
    SongStream song;
    RhythmState rhythm;

    size_t cur_section;
    size_t first_note;
    fixed_t note_scroll;
    fixed_t song_time;
    fixed_t player_scroll_speed;
    fixed_t opponent_scroll_speed;
    GameplayScrollTween scroll_tween;
    fixed_t event_time_scale;
    s32 song_step;
    u32 misses;

    boolean loaded;
    boolean audio_started;
    boolean paused;
    boolean dead;
    boolean finished;
    boolean block_scroll_events;

    GameplayFrameEvents events;
} GameplayState;

ChartResult Gameplay_Load(
    GameplayState *state,
    const char *chart_path,
    const char *inst_path,
    const char *voices_path,
    boolean kade,
    boolean ghost,
    fixed_t speed);
void Gameplay_Free(GameplayState *state);
boolean Gameplay_SetPaused(GameplayState *state, boolean paused);
boolean Gameplay_IsPaused(const GameplayState *state);
boolean Gameplay_IsDead(const GameplayState *state);
boolean Gameplay_IsFinished(const GameplayState *state);
boolean Gameplay_SetCountdownDelay(GameplayState *state, fixed_t delay_seconds);
boolean Gameplay_SeekIntro(
    GameplayState *state,
    fixed_t song_time,
    fixed_t note_scroll);
void Gameplay_Tick(GameplayState *state, const Pad *pad);
void Gameplay_PressLane(GameplayState *state, u8 lane);
void Gameplay_HoldLane(GameplayState *state, u8 lane);
fixed_t Gameplay_NoteDelta(const GameplayState *state, const Note *note);
fixed_t Gameplay_NoteSpeedForSide(const GameplayState *state, boolean opponent);

#endif
