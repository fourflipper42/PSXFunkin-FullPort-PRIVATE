#include "rhythm.h"
#include <string.h>

static fixed_t milliseconds_to_scroll(
    const RhythmState *state,
    u16 milliseconds)
{
    fixed_t seconds;
    if (state == NULL || state->step_crochet <= 0)
        return 0;
    seconds = FIXED_DEC(milliseconds, 1000);
    seconds = FIXED_MUL(seconds,
        state->judgement_rate > 0 ? state->judgement_rate : FIXED_DEC(1, 1));
    return FIXED_MUL(state->step_crochet, seconds);
}

static void rhythm_recalc_windows(RhythmState *state)
{
    if (state == NULL || state->step_crochet <= 0)
        return;

    if (state->kade) {
        state->early_safe = state->late_safe = state->step_crochet / 6;
        state->late_sus_safe = (state->late_safe * 3) >> 1;
        state->early_sus_safe = state->early_safe >> 1;
        state->sick_safe = state->late_safe * 27 / 100;
        state->good_safe = state->late_safe * 54 / 100;
        state->bad_safe = state->late_safe * 81 / 100;
        state->shit_safe = state->late_safe;
        return;
    }

    state->sick_safe = milliseconds_to_scroll(state, state->sick_window_ms);
    state->good_safe = milliseconds_to_scroll(state, state->good_window_ms);
    state->bad_safe = milliseconds_to_scroll(state, state->bad_window_ms);
    state->shit_safe = milliseconds_to_scroll(state, state->shit_window_ms);

    if (state->sick_safe < 1) state->sick_safe = 1;
    if (state->good_safe < state->sick_safe) state->good_safe = state->sick_safe;
    if (state->bad_safe < state->good_safe) state->bad_safe = state->good_safe;
    if (state->shit_safe < state->bad_safe) state->shit_safe = state->bad_safe;

    /* Modern V-Slice uses the miss threshold on both sides of the note. */
    state->early_safe = state->shit_safe;
    state->late_safe = state->shit_safe;
    state->early_sus_safe = state->shit_safe;
    state->late_sus_safe = state->shit_safe;
}

void Rhythm_Init(RhythmState *state, boolean kade, boolean ghost, fixed_t speed)
{
    memset(state, 0, sizeof(*state));
    state->kade = kade;
    state->ghost = ghost;
    state->speed = speed;
    state->health = 10000;
    state->sick_window_ms = 45;
    state->good_window_ms = 90;
    state->bad_window_ms = 135;
    state->shit_window_ms = 160;
    state->judgement_rate = FIXED_DEC(1, 1);
    state->health_gain_mult = FIXED_DEC(1, 1);
    state->health_loss_mult = FIXED_DEC(1, 1);
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
    rhythm_recalc_windows(state);
}

void Rhythm_SetJudgementWindowsMs(
    RhythmState *state,
    u16 sick_ms,
    u16 good_ms,
    u16 bad_ms,
    u16 shit_ms,
    fixed_t playback_rate)
{
    if (state == NULL)
        return;
    if (sick_ms < 1) sick_ms = 1;
    if (good_ms < sick_ms) good_ms = sick_ms;
    if (bad_ms < good_ms) bad_ms = good_ms;
    if (shit_ms < bad_ms) shit_ms = bad_ms;
    state->sick_window_ms = sick_ms;
    state->good_window_ms = good_ms;
    state->bad_window_ms = bad_ms;
    state->shit_window_ms = shit_ms;
    state->judgement_rate = playback_rate > 0
        ? playback_rate : FIXED_DEC(1, 1);
    rhythm_recalc_windows(state);
}

void Rhythm_SetHealthMultipliers(
    RhythmState *state,
    fixed_t gain_mult,
    fixed_t loss_mult)
{
    if (state == NULL)
        return;
    if (gain_mult < 0) gain_mult = 0;
    if (loss_mult < 0) loss_mult = 0;
    state->health_gain_mult = gain_mult;
    state->health_loss_mult = loss_mult;
}

void Rhythm_ApplyHealthChange(RhythmState *state, s32 amount)
{
    fixed_t multiplier;
    s32 scaled;
    s32 health;

    if (state == NULL || amount == 0)
        return;
    multiplier = amount > 0 ? state->health_gain_mult : state->health_loss_mult;
    if (multiplier < 0)
        multiplier = 0;
    scaled = (s32)(((s64)amount * multiplier) >> FIXED_SHIFT);
    health = (s32)state->health + scaled;
    if (health > 32767) health = 32767;
    if (health < -32768) health = -32768;
    state->health = (s16)health;
}

HitRating Rhythm_ClassifyHit(const RhythmState *state, fixed_t offset)
{
    if (offset < 0)
        offset = -offset;

    if (offset > state->bad_safe)
        return HIT_SHIT;
    if (offset > state->good_safe)
        return HIT_BAD;
    if (offset > state->sick_safe)
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
            Rhythm_ApplyHealthChange(state, -600);
            state->score -= 30;
            if (state->combo != 0) {
                state->combo = 0;
                result.combo_broken = true;
            }
            return result;
        }

        ++state->combo;
        state->score += kade_score_inc[result.rating];
        Rhythm_ApplyHealthChange(state, kade_health_inc[result.rating]);
        result.start_vocal = true;
        return result;
    }

    ++state->combo;
    state->score += vanilla_score_inc[result.rating];
    Rhythm_ApplyHealthChange(state, 230);
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

    Rhythm_ApplyHealthChange(state, state->kade ? -1000 : -400);
    state->score -= 1;
    return broke_combo;
}
