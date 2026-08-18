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

typedef struct GameplayFrameEvents {
    u8 player_hit_mask;
    u8 opponent_hit_mask;
    boolean player_missed;
    boolean mine_hit;
    boolean just_step;
    boolean song_event_fired;
    boolean camera_focus_changed;
    u8 camera_focus;
    u16 last_song_event_kind;
    const char *last_song_event_name;
    const char *last_song_event_value;
    HitRating last_rating;
} GameplayFrameEvents;

typedef struct GameplayState {
    ChartAsset chart;
    SongEventStream song_events;
    SongStream song;
    RhythmState rhythm;

    size_t cur_section;
    size_t first_note;
    fixed_t note_scroll;
    fixed_t song_time;
    s32 song_step;
    u32 misses;

    boolean loaded;
    boolean audio_started;
    boolean finished;

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
void Gameplay_Tick(GameplayState *state, const Pad *pad);
void Gameplay_PressLane(GameplayState *state, u8 lane);
void Gameplay_HoldLane(GameplayState *state, u8 lane);
fixed_t Gameplay_NoteDelta(const GameplayState *state, const Note *note);

#endif
