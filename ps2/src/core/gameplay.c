#include "gameplay.h"

#include "timer.h"
#include <string.h>

static const u16 lane_buttons[4] = {
    INPUT_LEFT, INPUT_DOWN, INPUT_UP, INPUT_RIGHT
};

static fixed_t note_fixed(const Note *note)
{
    return (fixed_t)note->pos << FIXED_SHIFT;
}

static s32 scroll_to_song_step(fixed_t scroll)
{
    s32 units = scroll >> FIXED_SHIFT;
    if (scroll < 0)
        units -= 11;
    return units / 12;
}

static void Gameplay_ResetEvents(GameplayState *state)
{
    memset(&state->events, 0, sizeof(state->events));
    state->events.last_rating = HIT_SICK;
}

static void Gameplay_RecalcScroll(GameplayState *state)
{
    fixed_t next_scroll =
        ((fixed_t)state->rhythm.step_base << FIXED_SHIFT) +
        FIXED_MUL(state->song_time - state->rhythm.time_base, state->rhythm.step_crochet);

    if (next_scroll > state->note_scroll) {
        s32 old_step = scroll_to_song_step(state->note_scroll);
        s32 new_step = scroll_to_song_step(next_scroll);
        if (old_step != new_step)
            state->events.just_step = true;
        state->note_scroll = next_scroll;
        state->song_step = new_step;
    }
}

static void Gameplay_UpdateSections(GameplayState *state)
{
    ChartView *chart = &state->chart.view;

    while (state->cur_section < chart->section_count) {
        Section *section = &chart->sections[state->cur_section];
        u16 end = section->end;
        u16 next_bpm;

        if (end == 0xFFFFu || state->note_scroll < 0 ||
            (u32)(state->note_scroll >> FIXED_SHIFT) < end)
            break;

        ++state->cur_section;
        if (state->cur_section >= chart->section_count)
            break;

        next_bpm = chart->sections[state->cur_section].flag & SECTION_FLAG_BPM_MASK;
        if (next_bpm != 0 && next_bpm != state->rhythm.last_bpm) {
            Rhythm_ChangeBPM(&state->rhythm, next_bpm, end);
            Gameplay_RecalcScroll(state);
        }
    }
}

static void Gameplay_LateMiss(GameplayState *state, Note *note)
{
    if (note->type & (NOTE_FLAG_HIT | NOTE_FLAG_OPPONENT | NOTE_FLAG_MINE))
        return;

    note->type |= NOTE_FLAG_HIT;
    SongStream_SetVoices(&state->song, false);

    if (note->type & NOTE_FLAG_SUSTAIN) {
        /* Kade-style sustain pieces only cut vocals; vanilla also keeps the
         * miss light. The sustain head/end owns the large miss penalty. */
        if (!state->rhythm.kade)
            state->rhythm.health -= 100;
        state->events.player_missed = true;
        return;
    }

    if (state->rhythm.combo != 0)
        state->rhythm.combo = 0;
    state->rhythm.health -= state->rhythm.kade
        ? ((note->type & NOTE_FLAG_SUSTAIN_END) ? 2000 : 1000)
        : 1000;
    state->rhythm.score -= 1;
    ++state->misses;
    state->events.player_missed = true;
}

static void Gameplay_ProcessAutomaticNotes(GameplayState *state)
{
    ChartView *chart = &state->chart.view;
    size_t i;

    for (i = state->first_note; i < chart->note_count; ++i) {
        Note *note = &chart->notes[i];
        fixed_t fp = note_fixed(note);
        fixed_t safe = (note->type & NOTE_FLAG_SUSTAIN)
            ? state->rhythm.late_sus_safe
            : state->rhythm.late_safe;

        if (fp > state->note_scroll + state->rhythm.early_safe)
            break;

        if ((note->type & NOTE_FLAG_OPPONENT) && !(note->type & NOTE_FLAG_HIT) &&
            fp <= state->note_scroll) {
            note->type |= NOTE_FLAG_HIT;
            state->events.opponent_hit_mask |= (u8)(1u << (note->type & 0x3));
            SongStream_SetVoices(&state->song, true);
            continue;
        }

        if (!(note->type & NOTE_FLAG_OPPONENT) && !(note->type & NOTE_FLAG_HIT) &&
            fp + safe < state->note_scroll)
            Gameplay_LateMiss(state, note);
    }

    while (state->first_note < chart->note_count) {
        Note *note = &chart->notes[state->first_note];
        fixed_t fp = note_fixed(note);
        fixed_t safe = (note->type & NOTE_FLAG_SUSTAIN)
            ? state->rhythm.late_sus_safe
            : state->rhythm.late_safe;

        if (!(note->type & NOTE_FLAG_HIT) || fp + safe >= state->note_scroll)
            break;
        ++state->first_note;
    }
}

ChartResult Gameplay_Load(
    GameplayState *state,
    const char *chart_path,
    const char *inst_path,
    const char *voices_path,
    boolean kade,
    boolean ghost,
    fixed_t speed)
{
    ChartResult result;
    u16 first_bpm;

    if (state == NULL || chart_path == NULL || inst_path == NULL)
        return CHART_ERR_NULL;

    memset(state, 0, sizeof(*state));
    result = ChartAsset_Load(&state->chart, chart_path);
    if (result != CHART_OK)
        return result;

    if (state->chart.view.section_count == 0) {
        Gameplay_Free(state);
        return CHART_ERR_TOO_SMALL;
    }

    if (!SongStream_Open(&state->song, inst_path, voices_path)) {
        Gameplay_Free(state);
        return CHART_ERR_IO;
    }

    Rhythm_Init(&state->rhythm, kade, ghost, speed);
    first_bpm = state->chart.view.sections[0].flag & SECTION_FLAG_BPM_MASK;
    if (first_bpm == 0) {
        Gameplay_Free(state);
        return CHART_ERR_SECTION_LAYOUT;
    }
    Rhythm_ChangeBPM(&state->rhythm, first_bpm, 0);

    state->note_scroll = -(192 << FIXED_SHIFT); /* four-beat-countdown pre-roll */
    state->song_time = FIXED_DIV(state->note_scroll, state->rhythm.step_crochet);
    state->song_step = scroll_to_song_step(state->note_scroll);
    state->loaded = true;
    Gameplay_ResetEvents(state);
    return CHART_OK;
}

void Gameplay_Free(GameplayState *state)
{
    if (state == NULL)
        return;
    SongStream_Close(&state->song);
    ChartAsset_Free(&state->chart);
    memset(state, 0, sizeof(*state));
}

void Gameplay_PressLane(GameplayState *state, u8 lane)
{
    ChartView *chart;
    size_t i;
    boolean hit = false;

    if (state == NULL || !state->loaded || lane > 3)
        return;

    chart = &state->chart.view;
    for (i = state->first_note; i < chart->note_count; ++i) {
        Note *note = &chart->notes[i];
        fixed_t fp = note_fixed(note);

        if (fp - state->rhythm.early_safe > state->note_scroll)
            break;
        if (fp + state->rhythm.late_safe < state->note_scroll)
            continue;
        if ((note->type & NOTE_FLAG_HIT) || (note->type & NOTE_FLAG_OPPONENT) ||
            (note->type & 0x3) != lane || (note->type & NOTE_FLAG_SUSTAIN))
            continue;

        if (note->type & NOTE_FLAG_MINE) {
            fixed_t early = state->rhythm.late_safe * 3 / 5;
            fixed_t late = state->rhythm.late_safe * 2 / 5;
            if (fp - early > state->note_scroll || fp + late < state->note_scroll)
                continue;
            note->type |= NOTE_FLAG_HIT;
            state->rhythm.health -= 2000;
            state->rhythm.combo = 0;
            state->events.mine_hit = true;
            SongStream_SetVoices(&state->song, false);
            hit = true;
            break;
        }

        note->type |= NOTE_FLAG_HIT;
        {
            RhythmHitResult result = Rhythm_ApplyHit(&state->rhythm, state->note_scroll - fp);
            state->events.last_rating = result.rating;
            state->events.player_hit_mask |= (u8)(1u << lane);
            if (result.cut_vocal)
                SongStream_SetVoices(&state->song, false);
            if (result.start_vocal)
                SongStream_SetVoices(&state->song, true);
        }
        hit = true;
        break;
    }

    if (!hit) {
        boolean broke = Rhythm_ApplyEmptyPressMiss(&state->rhythm);
        (void)broke;
        if (!state->rhythm.ghost) {
            ++state->misses;
            state->events.player_missed = true;
            SongStream_SetVoices(&state->song, false);
        }
    }
}

void Gameplay_HoldLane(GameplayState *state, u8 lane)
{
    ChartView *chart;
    size_t i;

    if (state == NULL || !state->loaded || lane > 3)
        return;

    chart = &state->chart.view;
    for (i = state->first_note; i < chart->note_count; ++i) {
        Note *note = &chart->notes[i];
        fixed_t fp = note_fixed(note);

        if (fp - state->rhythm.early_sus_safe > state->note_scroll)
            break;
        if (fp + state->rhythm.late_sus_safe < state->note_scroll)
            continue;
        if ((note->type & NOTE_FLAG_HIT) || (note->type & NOTE_FLAG_OPPONENT) ||
            (note->type & 0x3) != lane || !(note->type & NOTE_FLAG_SUSTAIN))
            continue;

        note->type |= NOTE_FLAG_HIT;
        state->events.player_hit_mask |= (u8)(1u << lane);
        SongStream_SetVoices(&state->song, true);
        if (!state->rhythm.kade)
            state->rhythm.health += 230;
        break;
    }
}

void Gameplay_Tick(GameplayState *state, const Pad *pad)
{
    fixed_t old_scroll;
    int lane;

    if (state == NULL || !state->loaded || state->finished)
        return;

    Gameplay_ResetEvents(state);
    old_scroll = state->note_scroll;

    if (!state->audio_started) {
        state->song_time += timer_dt;
        if (state->song_time >= 0) {
            state->song_time = 0;
            state->note_scroll = 0;
            state->song_step = 0;
            state->audio_started = true;
            SongStream_Tick(&state->song);
        } else {
            state->note_scroll = FIXED_MUL(state->song_time, state->rhythm.step_crochet);
            state->song_step = scroll_to_song_step(state->note_scroll);
            if (scroll_to_song_step(old_scroll) != state->song_step)
                state->events.just_step = true;
        }
    } else {
        SongStream_Tick(&state->song);
        state->song_time = SongStream_PlayedSeconds(&state->song);
        Gameplay_RecalcScroll(state);
    }

    Gameplay_UpdateSections(state);

    if (pad != NULL) {
        for (lane = 0; lane < 4; ++lane) {
            if (pad->press & lane_buttons[lane])
                Gameplay_PressLane(state, (u8)lane);
        }
        for (lane = 0; lane < 4; ++lane) {
            if (pad->held & lane_buttons[lane])
                Gameplay_HoldLane(state, (u8)lane);
        }
    }

    Gameplay_ProcessAutomaticNotes(state);
    if (state->audio_started && SongStream_Finished(&state->song))
        state->finished = true;
}

fixed_t Gameplay_NoteDelta(const GameplayState *state, const Note *note)
{
    if (state == NULL || note == NULL)
        return 0;
    return note_fixed(note) - state->note_scroll;
}
