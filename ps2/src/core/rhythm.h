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

    /* Modern Funkin/PBOT judgement windows, expressed in real milliseconds
     * then converted into chart-scroll units whenever BPM changes. */
    u16 sick_window_ms;
    u16 good_window_ms;
    u16 bad_window_ms;
    u16 shit_window_ms;
    fixed_t judgement_rate;
    fixed_t sick_safe;
    fixed_t good_safe;
    fixed_t bad_safe;
    fixed_t shit_safe;

    /* Gammod Health Gain/Loss. Positive and negative gameplay health changes
     * are scaled independently. Native drain mechanics deliberately bypass
     * these multipliers, matching the source modifiers. */
    fixed_t health_gain_mult;
    fixed_t health_loss_mult;

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
void Rhythm_SetJudgementWindowsMs(
    RhythmState *state,
    u16 sick_ms,
    u16 good_ms,
    u16 bad_ms,
    u16 shit_ms,
    fixed_t playback_rate);
void Rhythm_SetHealthMultipliers(
    RhythmState *state,
    fixed_t gain_mult,
    fixed_t loss_mult);
void Rhythm_ApplyHealthChange(RhythmState *state, s32 amount);
HitRating Rhythm_ClassifyHit(const RhythmState *state, fixed_t offset);
RhythmHitResult Rhythm_ApplyHit(RhythmState *state, fixed_t offset);
boolean Rhythm_ApplyEmptyPressMiss(RhythmState *state);

#endif
