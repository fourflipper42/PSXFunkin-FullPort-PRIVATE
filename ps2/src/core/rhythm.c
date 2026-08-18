#include "rhythm.h"
#include <string.h>

void Rhythm_Init(RhythmState *state, boolean kade, boolean ghost, fixed_t speed)
{
    memset(state, 0, sizeof(*state));
    state->kade = kade;
    state->ghost = ghost;
    state->speed = speed;
    state->health = 10000;
}

void Rhythm_ChangeBPM(RhythmState *state, u16 bpm, u16 step)
{
    fixed_t bpm_dec;

    state->last_bpm = bpm;

    if (state->step_crochet != 0) {
        state->time_base += FIXED_DIV(
            ((fixed_t)step - (fixed_t)state->step_base) << FIXED_SHIFT,
            state->step_crochet);
    }
    state->step_base = step;

    bpm_dec = ((fixed_t)bpm << FIXED_SHIFT) / 24;
    state->step_crochet = FIXED_DIV(bpm_dec, FIXED_DEC(125, 100));
    state->note_speed = FIXED_MUL(
        FIXED_DIV(FIXED_DEC(140, 1), state->step_crochet),
        state->speed);

    if (state->kade) {
        state->early_safe = state->late_safe = state->step_crochet / 6;
        state->late_sus_safe = (state->late_safe * 3) >> 1;
        state->early_sus_safe = state->early_safe >> 1;
    } else {
        state->late_safe = state->step_crochet / 6;
        state->early_safe = state->late_safe >> 1;
        state->late_sus_safe = state->late_safe;
        state->early_sus_safe = state->early_safe;
    }
}

HitRating Rhythm_ClassifyHit(const RhythmState *state, fixed_t offset)
{
    if (offset < 0)
        offset = -offset;

    if (state->kade) {
        if (offset > state->late_safe * 81 / 100)
            return HIT_SHIT;
        if (offset > state->late_safe * 54 / 100)
            return HIT_BAD;
        if (offset > state->late_safe * 27 / 100)
            return HIT_GOOD;
        return HIT_SICK;
    }

    if (offset > state->late_safe * 9 / 10)
        return HIT_SHIT;
    if (offset > state->late_safe * 3 / 4)
        return HIT_BAD;
    if (offset > state->late_safe / 5)
        return HIT_GOOD;
    return HIT_SICK;
}

RhythmHitResult Rhythm_ApplyHit(RhythmState *state, fixed_t offset)
{
    RhythmHitResult result;
    static const s32 kade_score_inc[4] = {35, 20, 0, -30};
    static const s16 kade_health_inc[4] = {400, 0, -300, -600};
    static const s32 vanilla_score_inc[4] = {35, 20, 10, 5};

    result.rating = Rhythm_ClassifyHit(state, offset);
    result.start_vocal = false;
    result.cut_vocal = false;
    result.combo_broken = false;

    ++state->judged_notes;
    ++state->rating_counts[(int)result.rating];

    if (state->kade) {
        if (result.rating == HIT_SHIT) {
            result.cut_vocal = true;
            state->health -= 600;
            state->score -= 30;
            if (state->combo != 0) {
                state->combo = 0;
                result.combo_broken = true;
            }
            return result;
        }

        ++state->combo;
        state->score += kade_score_inc[result.rating];
        state->health += kade_health_inc[result.rating];
        result.start_vocal = true;
        return result;
    }

    ++state->combo;
    state->score += vanilla_score_inc[result.rating];
    state->health += 230;
    result.start_vocal = true;
    return result;
}

boolean Rhythm_ApplyEmptyPressMiss(RhythmState *state)
{
    boolean broke_combo = false;

    if (state->ghost)
        return false;

    if (state->combo != 0) {
        state->combo = 0;
        broke_combo = true;
    }

    state->health -= state->kade ? 1000 : 400;
    state->score -= 1;
    return broke_combo;
}
