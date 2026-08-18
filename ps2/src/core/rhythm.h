#ifndef FNF_PS2_RHYTHM_H
#define FNF_PS2_RHYTHM_H

#include "fixed.h"

typedef enum HitRating {
    HIT_SICK = 0,
    HIT_GOOD = 1,
    HIT_BAD = 2,
    HIT_SHIT = 3
} HitRating;

typedef struct RhythmState {
    boolean kade;
    boolean ghost;
    fixed_t speed;

    u16 last_bpm;
    u16 step_base;
    fixed_t time_base;
    fixed_t step_crochet;
    fixed_t early_safe;
    fixed_t late_safe;
    fixed_t early_sus_safe;
    fixed_t late_sus_safe;
    fixed_t note_speed;

    s16 health;
    u16 combo;
    s32 score;

    /* Head-note judgement totals. Sustains do not increment these, matching
     * Funkin's rating/accuracy semantics and Pointless Pins' All Sicks check. */
    u32 judged_notes;
    u32 rating_counts[4];
} RhythmState;

typedef struct RhythmHitResult {
    HitRating rating;
    boolean start_vocal;
    boolean cut_vocal;
    boolean combo_broken;
} RhythmHitResult;

void Rhythm_Init(RhythmState *state, boolean kade, boolean ghost, fixed_t speed);
void Rhythm_ChangeBPM(RhythmState *state, u16 bpm, u16 step);
HitRating Rhythm_ClassifyHit(const RhythmState *state, fixed_t offset);
RhythmHitResult Rhythm_ApplyHit(RhythmState *state, fixed_t offset);
boolean Rhythm_ApplyEmptyPressMiss(RhythmState *state);

#endif
