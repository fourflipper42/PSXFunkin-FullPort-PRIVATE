#include "gameplay.h"

#include "timer.h"
#include <stdio.h>
#include <string.h>

#define GAMEPLAY_HEALTH_MAX 20000

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

static boolean Gameplay_EventPath(
    char *out,
    size_t out_size,
    const char *chart_path)
{
    const char *slash;
    const char *backslash;
    const char *separator;
    const char *filename;
    const char *version;
    size_t prefix_len;
    int written;

    if (out == NULL || out_size == 0 || chart_path == NULL)
        return false;

    slash = strrchr(chart_path, '/');
    backslash = strrchr(chart_path, '\\');
    if (slash == NULL)
        separator = backslash;
    else if (backslash == NULL)
        separator = slash;
    else
        separator = slash > backslash ? slash : backslash;

    filename = separator != NULL ? separator + 1 : chart_path;
    prefix_len = separator != NULL ? (size_t)(separator - chart_path + 1) : 0;
    version = strstr(filename, ";1");

    written = snprintf(
        out,
        out_size,
        "%.*sEVENTS.FEVT%s",
        (int)prefix_len,
        chart_path,
        version != NULL ? ";1" : "");
    return written >= 0 && (size_t)written < out_size;
}

static void Gameplay_DispatchSongEvent(
    void *user,
    const SongEventRecord *event,
    const char *name,
    const char *value_json)
{
    GameplayState *state = (GameplayState *)user;
    GameplayFrameEvents *frame;

    if (state == NULL || event == NULL)
        return;

    frame = &state->events;
    frame->song_event_fired = true;
    frame->last_song_event_kind = event->kind;
    frame->last_song_event_name = name;
    frame->last_song_event_value = value_json;

    if (frame->song_event_count < GAMEPLAY_FRAME_SONG_EVENT_MAX) {
        GameplaySongEventFrame *queued =
            &frame->song_events[frame->song_event_count++];
        queued->kind = event->kind;
        queued->name = name;
        queued->value = value_json;
    } else {
        frame->song_event_overflow = true;
    }

    if (event->kind == SONG_EVENT_FOCUS_CAMERA) {
        s32 focus = (s32)(event->arg0 + 0.5f);
        if (focus >= 0 && focus <= 2) {
            frame->camera_focus_changed = true;
            frame->camera_focus = (u8)focus;
        }
    }
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
        if (!state->rhythm.kade)
            Rhythm_ApplyHealthChange(&state->rhythm, -100);
        state->events.player_missed = true;
        return;
    }

    if (state->rhythm.combo != 0)
        state->rhythm.combo = 0;
    Rhythm_ApplyHealthChange(
        &state->rhythm,
        state->rhythm.kade
            ? ((note->type & NOTE_FLAG_SUSTAIN_END) ? -2000 : -1000)
            : -1000);
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

static boolean Gameplay_CheckHealth(GameplayState *state)
{
    if (state->rhythm.health > GAMEPLAY_HEALTH_MAX)
        state->rhythm.health = GAMEPLAY_HEALTH_MAX;

    if (state->rhythm.health > 0 || state->dead)
        return state->dead;

    state->rhythm.health = 0;
    state->dead = true;
    state->paused = true;
    state->events.player_died = true;

    if (state->audio_started && !SongStream_Paused(&state->song))
        SongStream_Pause(&state->song);
    return true;
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
    char event_path[256];

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

    if (Gameplay_EventPath(event_path, sizeof(event_path), chart_path)) {
        if (SongEvents_Load(&state->song_events, event_path)) {
            SongEvents_Reset(&state->song_events);
            printf("[PS2] chart events loaded: %u\n",
                (unsigned)state->song_events.count);
        }
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
    state->player_scroll_speed = state->rhythm.speed;
    state->opponent_scroll_speed = state->rhythm.speed;
    state->event_time_scale = FIXED_DEC(1, 1);
    state->block_scroll_events = false;

    state->note_scroll = -(192 << FIXED_SHIFT);
    state->song_time = FIXED_DIV(state->note_scroll, state->rhythm.step_crochet);
    state->song_step = scroll_to_song_step(state->note_scroll);
    state->loaded = true;
    state->paused = false;
    state->dead = false;
    state->finished = false;
    Gameplay_ResetEvents(state);
    return CHART_OK;
}

void Gameplay_Free(GameplayState *state)
{
    if (state == NULL)
        return;
    SongStream_Close(&state->song);
    SongEvents_Free(&state->song_events);
    ChartAsset_Free(&state->chart);
    memset(state, 0, sizeof(*state));
}

boolean Gameplay_SetPaused(GameplayState *state, boolean paused)
{
    if (state == NULL || !state->loaded || state->dead || state->finished)
        return false;
    if (state->paused == paused)
        return true;

    if (paused) {
        if (state->audio_started && !SongStream_Pause(&state->song))
            return false;
        state->paused = true;
        return true;
    }

    if (state->audio_started && !SongStream_Resume(&state->song))
        return false;
    state->paused = false;
    return true;
}

boolean Gameplay_IsPaused(const GameplayState *state)
{
    return state != NULL && state->paused;
}

boolean Gameplay_IsDead(const GameplayState *state)
{
    return state != NULL && state->dead;
}

boolean Gameplay_IsFinished(const GameplayState *state)
{
    return state != NULL && state->finished;
}

boolean Gameplay_SetCountdownDelay(GameplayState *state, fixed_t delay_seconds)
{
    if (state == NULL || !state->loaded || state->audio_started ||
        state->dead || state->finished)
        return false;
    if (delay_seconds < 0)
        delay_seconds = 0;
    if (delay_seconds > FIXED_DEC(2, 1))
        delay_seconds = FIXED_DEC(2, 1);

    state->song_time = -delay_seconds;
    state->note_scroll = FIXED_MUL(state->song_time, state->rhythm.step_crochet);
    state->song_step = scroll_to_song_step(state->note_scroll);
    return true;
}

boolean Gameplay_SeekIntro(
    GameplayState *state,
    fixed_t song_time,
    fixed_t note_scroll)
{
    u64 frame;

    if (state == NULL || !state->loaded || song_time < 0 || note_scroll < 0 ||
        state->dead || state->finished)
        return false;

    frame = ((u64)(u32)song_time * AUDIO_SAMPLE_RATE) >> FIXED_SHIFT;
    if (!SongStream_SeekFrame(&state->song, frame))
        return false;

    state->song_time = song_time;
    state->note_scroll = note_scroll;
    state->song_step = scroll_to_song_step(note_scroll);
    state->cur_section = 0;
    state->first_note = 0;
    state->audio_started = true;
    state->paused = false;
    state->dead = false;
    state->finished = false;
    Gameplay_ResetEvents(state);
    if (state->song_events.loaded)
        SongEvents_Reset(&state->song_events);
    Gameplay_UpdateSections(state);
    return true;
}

void Gameplay_PressLane(GameplayState *state, u8 lane)
{
    ChartView *chart;
    size_t i;
    boolean hit = false;

    if (state == NULL || !state->loaded || state->paused || state->dead ||
        state->finished || lane > 3)
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
            Rhythm_ApplyHealthChange(&state->rhythm, -2000);
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

    if (state == NULL || !state->loaded || state->paused || state->dead ||
        state->finished || lane > 3)
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
            Rhythm_ApplyHealthChange(&state->rhythm, 230);
        break;
    }
}

void Gameplay_Tick(GameplayState *state, const Pad *pad)
{
    fixed_t old_scroll;
    int lane;

    if (state == NULL || !state->loaded || state->paused || state->dead || state->finished)
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

    if (state->song_events.loaded) {
        SongEvents_Tick(
            &state->song_events,
            state->song_time,
            Gameplay_DispatchSongEvent,
            state);
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
    if (Gameplay_CheckHealth(state))
        return;

    if (state->audio_started && SongStream_Finished(&state->song)) {
        state->finished = true;
        state->events.song_finished = true;
    }
}

fixed_t Gameplay_NoteDelta(const GameplayState *state, const Note *note)
{
    if (state == NULL || note == NULL)
        return 0;
    return note_fixed(note) - state->note_scroll;
}
