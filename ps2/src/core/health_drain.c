#include "health_drain.h"

#include <string.h>

#define HEALTH_DRAIN_MAX_HEALTH       20000
#define HEALTH_DRAIN_NORMAL_FLOOR      1000
#define HEALTH_DRAIN_ABSURD_HEALTH      500
#define HEALTH_DRAIN_SICK_UNITS         300
#define HEALTH_DRAIN_HOLD_UNITS_SEC     960
#define HEALTH_DRAIN_SUSTAIN_WINDOW      16

static float health_drain_auto_multiplier(HealthDrain *drain, const GameplayState *game)
{
    float health;
    float target = 1.0f;

    if (drain == NULL || game == NULL)
        return 1.0f;

    health = (float)game->rhythm.health / 10000.0f;

    if (game->misses >= 6)
        target = 0.5f;
    else if (game->misses >= 3)
        target = 0.7f;
    else if (game->misses >= 1)
        target = 0.85f;
    else if (game->rhythm.combo >= 50)
        target = 1.9f;
    else if (game->rhythm.combo >= 30)
        target = 1.35f;
    else if (game->rhythm.combo >= 15)
        target = 1.15f;
    else if (game->rhythm.combo >= 5)
        target = 1.0f;

    if (health < 0.25f)
        target *= 0.8f;
    else if (health > 0.8f)
        target *= 1.08f;

    target *= drain->lag_multiplier;
    if (target > 2.0f) target = 2.0f;
    if (target < 0.5f) target = 0.5f;

    drain->auto_multiplier += (target - drain->auto_multiplier) * 0.12f;
    return drain->auto_multiplier;
}

static float health_drain_multiplier(HealthDrain *drain, const GameplayState *game)
{
    switch (drain != NULL ? drain->level : HEALTH_DRAIN_OFF) {
        case HEALTH_DRAIN_OFF: return 0.0f;
        case HEALTH_DRAIN_NOOB: return 0.5f;
        case HEALTH_DRAIN_EASY: return 0.7f;
        case HEALTH_DRAIN_NORMAL: return 1.0f;
        case HEALTH_DRAIN_HARD: return 2.0f;
        case HEALTH_DRAIN_INSANE: return 3.0f;
        case HEALTH_DRAIN_AUTO_PRO: return health_drain_auto_multiplier(drain, game);
        case HEALTH_DRAIN_ABSURD: return 0.0f;
        default: return 1.0f;
    }
}

static boolean health_drain_opponent_tap_this_frame(
    const GameplayState *game,
    u8 lane)
{
    const ChartView *chart;
    size_t i;
    s32 current;

    if (game == NULL || !game->loaded)
        return false;
    chart = &game->chart.view;
    current = game->note_scroll >> FIXED_SHIFT;

    /* The gameplay bridge exposes opponent hit lanes as a mask. Distinguish
     * tap heads from generated sustain pieces by looking at already-hit notes
     * nearest the current 1/12-step position. */
    for (i = 0; i < chart->note_count; ++i) {
        const Note *note = &chart->notes[i];
        s32 delta;
        if (!(note->type & NOTE_FLAG_HIT) || !(note->type & NOTE_FLAG_OPPONENT) ||
            (note->type & 3) != (lane & 3))
            continue;
        delta = (s32)note->pos - current;
        if (delta < -2 || delta > 2)
            continue;
        if (!(note->type & NOTE_FLAG_SUSTAIN))
            return true;
    }
    return false;
}

static boolean health_drain_any_opponent_hold_active(const GameplayState *game)
{
    const ChartView *chart;
    s32 current;
    int lane;

    if (game == NULL || !game->loaded)
        return false;
    chart = &game->chart.view;
    current = game->note_scroll >> FIXED_SHIFT;

    for (lane = 0; lane < 4; ++lane) {
        const Note *latest = NULL;
        size_t i;

        for (i = 0; i < chart->note_count; ++i) {
            const Note *note = &chart->notes[i];
            s32 delta;
            if (!(note->type & NOTE_FLAG_HIT) || !(note->type & NOTE_FLAG_OPPONENT) ||
                !(note->type & NOTE_FLAG_SUSTAIN) ||
                (note->type & 3) != lane)
                continue;
            delta = current - (s32)note->pos;
            if (delta < 0 || delta > HEALTH_DRAIN_SUSTAIN_WINDOW)
                continue;
            if (latest == NULL || note->pos > latest->pos)
                latest = note;
        }

        if (latest != NULL && !(latest->type & NOTE_FLAG_SUSTAIN_END))
            return true;
    }
    return false;
}

static void health_drain_subtract(GameplayState *game, s32 amount, s32 floor)
{
    if (game == NULL || amount <= 0 || game->rhythm.health <= floor)
        return;
    game->rhythm.health -= amount;
    if (game->rhythm.health < floor)
        game->rhythm.health = floor;
}

void HealthDrain_Init(HealthDrain *drain, HealthDrainLevel level)
{
    if (drain == NULL)
        return;
    memset(drain, 0, sizeof(*drain));
    drain->auto_multiplier = 1.0f;
    drain->lag_multiplier = 1.0f;
    HealthDrain_SetLevel(drain, NULL, level);
}

void HealthDrain_SetLevel(
    HealthDrain *drain,
    GameplayState *game,
    HealthDrainLevel level)
{
    boolean was_absurd;

    if (drain == NULL)
        return;
    if (level < HEALTH_DRAIN_OFF || level >= HEALTH_DRAIN_LEVEL_COUNT)
        level = HEALTH_DRAIN_AUTO_PRO;

    was_absurd = drain->level == HEALTH_DRAIN_ABSURD;
    drain->level = level;
    drain->absurd_failed = false;
    drain->auto_multiplier = 1.0f;

    if (level == HEALTH_DRAIN_ABSURD && game != NULL)
        game->rhythm.health = HEALTH_DRAIN_ABSURD_HEALTH;
    else if (was_absurd && game != NULL && game->rhythm.health < HEALTH_DRAIN_NORMAL_FLOOR)
        game->rhythm.health = HEALTH_DRAIN_NORMAL_FLOOR;
}

void HealthDrain_OnFrame(
    HealthDrain *drain,
    GameplayState *game,
    fixed_t elapsed)
{
    float elapsed_seconds;
    float multiplier;
    int lane;

    if (drain == NULL || game == NULL || !game->loaded ||
        game->paused || game->dead || game->finished)
        return;

    elapsed_seconds = (float)elapsed / (float)FIXED_UNIT;
    if (elapsed_seconds > 0.06f)
        drain->lag_multiplier = 0.75f;
    else if (elapsed_seconds > 0.045f)
        drain->lag_multiplier = 0.90f;
    else
        drain->lag_multiplier = 1.0f;

    if (drain->level == HEALTH_DRAIN_OFF)
        return;

    if (drain->level == HEALTH_DRAIN_ABSURD) {
        if (game->events.player_missed || game->rhythm.health < HEALTH_DRAIN_ABSURD_HEALTH) {
            drain->absurd_failed = true;
            game->rhythm.health = 0;
            return;
        }
        game->rhythm.health = HEALTH_DRAIN_ABSURD_HEALTH;
        return;
    }

    if (drain->absurd_failed)
        return;

    for (lane = 0; lane < 4; ++lane) {
        if ((game->events.opponent_hit_mask & (1u << lane)) &&
            health_drain_opponent_tap_this_frame(game, (u8)lane)) {
            multiplier = health_drain_multiplier(drain, game) * drain->lag_multiplier;
            health_drain_subtract(
                game,
                (s32)((float)HEALTH_DRAIN_SICK_UNITS * multiplier + 0.5f),
                HEALTH_DRAIN_NORMAL_FLOOR);
        }
    }

    if (health_drain_any_opponent_hold_active(game)) {
        multiplier = health_drain_multiplier(drain, game) * drain->lag_multiplier;
        health_drain_subtract(
            game,
            (s32)((float)HEALTH_DRAIN_HOLD_UNITS_SEC * multiplier * elapsed_seconds + 0.5f),
            HEALTH_DRAIN_NORMAL_FLOOR);
    }

    if (game->rhythm.health > HEALTH_DRAIN_MAX_HEALTH)
        game->rhythm.health = HEALTH_DRAIN_MAX_HEALTH;
}

const char *HealthDrain_LevelName(HealthDrainLevel level)
{
    static const char *names[HEALTH_DRAIN_LEVEL_COUNT] = {
        "OFF", "Noob", "Easy", "Normal", "Hard", "Insane", "AUTO PRO", "ABSURD"
    };
    if (level < HEALTH_DRAIN_OFF || level >= HEALTH_DRAIN_LEVEL_COUNT)
        level = HEALTH_DRAIN_AUTO_PRO;
    return names[level];
}

float HealthDrain_CurrentMultiplier(const HealthDrain *drain)
{
    if (drain == NULL)
        return 0.0f;
    if (drain->level == HEALTH_DRAIN_AUTO_PRO)
        return drain->auto_multiplier * drain->lag_multiplier;
    switch (drain->level) {
        case HEALTH_DRAIN_NOOB: return 0.5f;
        case HEALTH_DRAIN_EASY: return 0.7f;
        case HEALTH_DRAIN_NORMAL: return 1.0f;
        case HEALTH_DRAIN_HARD: return 2.0f;
        case HEALTH_DRAIN_INSANE: return 3.0f;
        default: return 0.0f;
    }
}
