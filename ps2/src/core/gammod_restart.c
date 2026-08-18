#include "gammod.h"

static fixed_t restart_float_fixed(float value)
{
    return (fixed_t)(value * (float)FIXED_UNIT + (value >= 0.0f ? 0.5f : -0.5f));
}

static float restart_clampf(float value, float low, float high)
{
    if (value < low) return low;
    if (value > high) return high;
    return value;
}

static fixed_t restart_chart_time_for_pos(const GameplayState *game, u16 pos)
{
    const ChartView *chart;
    u32 start = 0;
    u16 bpm = 100 * 24;
    float seconds = 0.0f;
    size_t i;

    if (game == NULL)
        return 0;
    chart = &game->chart.view;
    for (i = 0; i < chart->section_count && start < pos; ++i) {
        const Section *section = &chart->sections[i];
        u32 end;
        u16 value = section->flag & SECTION_FLAG_BPM_MASK;
        u32 segment_end;
        float actual_bpm;
        float units_per_second;

        if (value != 0)
            bpm = value;
        end = section->end == 0xFFFFu ? (u32)pos : (u32)section->end;
        segment_end = end < (u32)pos ? end : (u32)pos;
        if (segment_end > start) {
            actual_bpm = (float)bpm / 24.0f;
            units_per_second = actual_bpm * 0.8f;
            if (units_per_second > 0.0f)
                seconds += (float)(segment_end - start) / units_per_second;
        }
        if (end >= (u32)pos || section->end == 0xFFFFu)
            break;
        start = end;
    }
    return restart_float_fixed(seconds);
}

static void restart_configure_timing(GammodRuntime *runtime, GameplayState *game)
{
    float rate_float;
    fixed_t rate;
    fixed_t base_speed;
    fixed_t player_speed;
    fixed_t opponent_speed;
    fixed_t factor;

    rate_float = restart_clampf(runtime->config.playback_rate, 0.5f, 3.0f);
    runtime->config.playback_rate = rate_float;
    rate = restart_float_fixed(rate_float);
    SongStream_SetPlaybackRate(&game->song, rate);

    Rhythm_SetJudgementWindowsMs(
        &game->rhythm,
        runtime->config.custom_judgements ? runtime->config.sick_window_ms : 45,
        runtime->config.custom_judgements ? runtime->config.good_window_ms : 90,
        runtime->config.custom_judgements ? runtime->config.bad_window_ms : 135,
        runtime->config.custom_judgements ? runtime->config.shit_window_ms : 160,
        rate);
    Rhythm_SetHealthMultipliers(
        &game->rhythm,
        restart_float_fixed(restart_clampf(runtime->config.health_gain, 0.0f, 66.0f)),
        restart_float_fixed(restart_clampf(runtime->config.health_loss, 0.0f, 25.0f)));

    game->rhythm.ghost = runtime->config.ghost_tapping;
    game->block_scroll_events = !runtime->config.scroll_velocities;
    game->event_time_scale = runtime->config.playback_match_event_durations
        ? rate : FIXED_DEC(1, 1);

    base_speed = game->base_scroll_speed > 0
        ? game->base_scroll_speed : FIXED_DEC(1, 1);
    player_speed = base_speed;
    opponent_speed = base_speed;
    factor = runtime->config.playback_match_scroll_speed
        ? rate : FIXED_DEC(1, 1);

    if (runtime->config.custom_scroll_speed_enabled) {
        fixed_t player_value = restart_float_fixed(
            restart_clampf(runtime->config.custom_scroll_speed, 0.1f, 20.0f));
        fixed_t opponent_value = runtime->config.custom_scroll_opponent_separate
            ? restart_float_fixed(restart_clampf(
                runtime->config.custom_opponent_scroll_speed, 0.1f, 20.0f))
            : player_value;
        player_value = FIXED_MUL(player_value, factor);
        opponent_value = FIXED_MUL(opponent_value, factor);
        if (runtime->config.custom_scroll_as_multiplier) {
            player_speed = FIXED_MUL(base_speed, player_value);
            opponent_speed = FIXED_MUL(base_speed, opponent_value);
        } else {
            player_speed = player_value;
            opponent_speed = opponent_value;
        }
    }

    if (!runtime->config.playback_match_scroll_speed && rate != FIXED_DEC(1, 1)) {
        player_speed = FIXED_DIV(player_speed, rate);
        opponent_speed = FIXED_DIV(opponent_speed, rate);
    }
    if (player_speed < FIXED_DEC(1, 10)) player_speed = FIXED_DEC(1, 10);
    if (opponent_speed < FIXED_DEC(1, 10)) opponent_speed = FIXED_DEC(1, 10);

    game->rhythm.speed = player_speed;
    game->player_scroll_speed = player_speed;
    game->opponent_scroll_speed = opponent_speed;
    Rhythm_ChangeBPM(&game->rhythm, game->rhythm.last_bpm, game->rhythm.step_base);
}

static void restart_prepare_intro_skip(GammodRuntime *runtime, const GameplayState *game)
{
    const ChartView *chart;
    size_t i;
    u16 first_pos = 0;
    u32 safety_units;
    u16 target;

    runtime->intro_skip_pending = false;
    runtime->intro_skip_time = 0;
    runtime->intro_skip_scroll = 0;
    if (runtime->config.skip_silence != GAMMOD_SKIP_SILENCE_INTRO ||
        game == NULL || !game->loaded)
        return;

    chart = &game->chart.view;
    for (i = 0; i < chart->note_count; ++i) {
        const Note *note = &chart->notes[i];
        if (note->pos == 0xFFFFu || (note->type & NOTE_FLAG_SUSTAIN))
            continue;
        if (!runtime->config.skip_count_enemy_notes &&
            (note->type & NOTE_FLAG_OPPONENT))
            continue;
        first_pos = note->pos;
        break;
    }
    if (first_pos == 0)
        return;

    safety_units = (u32)runtime->config.skip_safety_beats * 48u;
    target = first_pos > safety_units ? (u16)(first_pos - safety_units) : 0;
    if (target == 0)
        return;
    runtime->intro_skip_scroll = (fixed_t)target << FIXED_SHIFT;
    runtime->intro_skip_time = restart_chart_time_for_pos(game, target);
    runtime->intro_skip_pending = runtime->intro_skip_time > 0;
}

boolean Gammod_RestartAttempt(GammodRuntime *runtime, GameplayState *game)
{
    if (runtime == NULL || game == NULL || !game->loaded)
        return false;
    if (!Gameplay_RestartAttempt(game))
        return false;

    runtime->perfect_failed = false;
    restart_configure_timing(runtime, game);
    Gammod_ApplyStartingHealth(runtime, game);
    if (runtime->config.skip_countdown) {
        Gameplay_SetCountdownDelay(
            game,
            restart_float_fixed(restart_clampf(
                runtime->config.skip_countdown_delay, 0.0f, 2.0f)));
    }
    restart_prepare_intro_skip(runtime, game);
    return true;
}
