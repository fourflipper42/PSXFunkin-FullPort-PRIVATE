#include "gammod.h"

#include "mem.h"
#include <stdlib.h>
#include <string.h>

#define GAMMOD_SAVE_MARKER 0x474E
#define GAMMOD_NOTE_MARGIN_MS 100
#define GAMMOD_HOLD_DRAIN_UNITS_SEC 960
#define GAMMOD_DRAIN_FLOOR 100

#define GMS_AUTOPLAY 0
#define GMS_LONG_NOTES 1
#define GMS_PLACEMENT 2
#define GMS_PERFECT 3
#define GMS_SIDE 4
#define GMS_SKIP_SILENCE 5
#define GMS_EXTRA 6
#define GMS_GHOST 7
#define GMS_SCROLL_VELOCITIES 8
#define GMS_CUSTOM_JUDGEMENTS 9
#define GMS_CUSTOM_SCROLL_ENABLED 10
#define GMS_CUSTOM_SCROLL_X10 11
#define GMS_HEALTH_DRAIN_X10 12
#define GMS_HEALTH_GAIN_X10 13
#define GMS_HEALTH_LOSS_X10 14
#define GMS_PLAYBACK_X100 15
#define GMS_RESET_ON_DEATH 16
#define GMS_SKIP_COUNTDOWN 17
#define GMS_STARTING_HEALTH 18
#define GMS_AVOID_JACKS 19
#define GMS_SICK_WINDOW 20
#define GMS_GOOD_WINDOW 21
#define GMS_BAD_WINDOW 22
#define GMS_SHIT_WINDOW 23
#define GMS_SKIP_SAFETY 24
#define GMS_COUNT_ENEMY 25
#define GMS_PERFECT_FAIL_GHOST 26
#define GMS_AUTOPLAY_ACT_OPP 27
#define GMS_PLAYBACK_FLAGS 28
#define GMS_CUSTOM_OPP_SCROLL_X10 29
#define GMS_MISC_FLAGS 30
#define GMS_MARKER 31

#define PLAYBACK_FLAG_STAGE       (1 << 0)
#define PLAYBACK_FLAG_EVENTS      (1 << 1)
#define PLAYBACK_FLAG_SCROLL      (1 << 2)

#define MISC_FLAG_OPP_SEPARATE    (1 << 0)
#define MISC_FLAG_SCROLL_MULT     (1 << 1)
#define MISC_COUNTDOWN_SHIFT      2
#define MISC_COUNTDOWN_MASK       (0x1F << MISC_COUNTDOWN_SHIFT)

static u16 gammod_lane_button(u8 lane)
{
    static const u16 buttons[4] = {
        INPUT_LEFT, INPUT_DOWN, INPUT_UP, INPUT_RIGHT
    };
    return buttons[lane & 3];
}

static fixed_t gammod_float_fixed(float value)
{
    return (fixed_t)(value * (float)FIXED_UNIT + (value >= 0.0f ? 0.5f : -0.5f));
}

static float gammod_clampf(float value, float low, float high)
{
    if (value < low) return low;
    if (value > high) return high;
    return value;
}

static u32 gammod_rand(u32 *seed)
{
    *seed = (*seed * 1664525u) + 1013904223u;
    return *seed;
}

static int note_compare(const void *a, const void *b)
{
    const Note *na = (const Note *)a;
    const Note *nb = (const Note *)b;
    if (na->pos < nb->pos) return -1;
    if (na->pos > nb->pos) return 1;
    if ((na->type & NOTE_FLAG_OPPONENT) != (nb->type & NOTE_FLAG_OPPONENT))
        return (na->type & NOTE_FLAG_OPPONENT) ? -1 : 1;
    return (int)(na->type & 3) - (int)(nb->type & 3);
}

static boolean same_lane_side(const Note *a, const Note *b)
{
    if (a == NULL || b == NULL)
        return false;
    return (a->type & (NOTE_FLAG_OPPONENT | 3)) ==
        (b->type & (NOTE_FLAG_OPPONENT | 3));
}

static u16 bpm_for_pos(const GameplayState *game, u16 pos)
{
    const ChartView *chart;
    u16 bpm = 100;
    size_t i;

    if (game == NULL)
        return bpm;
    chart = &game->chart.view;
    for (i = 0; i < chart->section_count; ++i) {
        const Section *section = &chart->sections[i];
        u16 value = section->flag & SECTION_FLAG_BPM_MASK;
        if (value != 0)
            bpm = (u16)(value / 24u);
        if (section->end == 0xFFFFu || pos < section->end)
            break;
    }
    return bpm == 0 ? 1 : bpm;
}

static fixed_t chart_time_for_pos(const GameplayState *game, u16 pos)
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
        float actual_bpm;
        float units_per_second;
        u32 segment_end;

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
    return gammod_float_fixed(seconds);
}

static size_t transform_capacity(const ChartView *chart)
{
    u16 max_pos = 0;
    size_t i;
    size_t cap;

    if (chart == NULL)
        return 0;
    for (i = 0; i < chart->note_count; ++i) {
        if (chart->notes[i].pos > max_pos)
            max_pos = chart->notes[i].pos;
    }
    cap = chart->note_count * 4u + ((size_t)max_pos / 6u) + 2048u;
    if (cap < chart->note_count)
        return 0;
    return cap;
}

static void transform_note_placement(
    Note *notes,
    size_t count,
    GammodNotePlacement mode,
    boolean avoid_jacks)
{
    size_t i;
    u32 seed = 1;
    s8 previous[2] = {-1, -1};

    if (notes == NULL || mode == GAMMOD_PLACEMENT_NORMAL)
        return;

    for (i = 0; i < count; ++i) {
        Note *note = &notes[i];
        u8 lane = note->type & 3;
        u8 side = (note->type & NOTE_FLAG_OPPONENT) ? 1 : 0;
        u8 next;

        if (mode == GAMMOD_PLACEMENT_MIRROR) {
            lane = 3 - lane;
        } else {
            do {
                next = (u8)(gammod_rand(&seed) & 3u);
            } while (avoid_jacks && previous[side] == (s8)next);
            lane = next;
            previous[side] = (s8)lane;
        }
        note->type = (note->type & ~3u) | lane;
    }
}

static boolean transform_player_side(Note *notes, size_t *count, size_t capacity, GammodPlayerSide side)
{
    size_t original;
    size_t i;

    if (notes == NULL || count == NULL || side == GAMMOD_SIDE_NORMAL)
        return true;

    original = *count;
    if (side == GAMMOD_SIDE_OPPOSITE) {
        for (i = 0; i < original; ++i)
            notes[i].type ^= NOTE_FLAG_OPPONENT;
        return true;
    }

    if (original > capacity - *count)
        return false;
    for (i = 0; i < original; ++i) {
        Note copy = notes[i];
        copy.type ^= NOTE_FLAG_OPPONENT;
        copy.type &= (u8)~NOTE_FLAG_HIT;
        notes[(*count)++] = copy;
    }
    return true;
}

static boolean transform_extra_notes(Note *notes, size_t *count, size_t capacity)
{
    size_t original;
    size_t i;
    u32 seed = 0xE17A1234u;

    if (notes == NULL || count == NULL)
        return false;
    original = *count;
    for (i = 0; i < original; ++i) {
        const Note *note = &notes[i];
        Note extra;
        u8 lane;
        if (note->type & NOTE_FLAG_SUSTAIN)
            continue;
        if (*count >= capacity)
            return false;
        lane = (u8)(gammod_rand(&seed) & 3u);
        if (lane == (note->type & 3))
            lane = (lane + 1u + (u8)(gammod_rand(&seed) % 3u)) & 3u;
        extra = *note;
        extra.type = (extra.type & ~3u) | lane;
        extra.type &= (u8)~NOTE_FLAG_HIT;
        notes[(*count)++] = extra;
    }
    return true;
}

typedef struct GammodHead {
    Note note;
    boolean had_sustain;
} GammodHead;

static boolean transform_long_notes(
    GammodRuntime *runtime,
    GameplayState *game,
    Note *notes,
    size_t *count,
    size_t capacity)
{
    GammodHead *heads;
    size_t head_count = 0;
    size_t i;
    s32 last_head[2][4];
    size_t out = 0;

    if (runtime->config.long_notes == GAMMOD_LONG_NORMAL)
        return true;

    memset(last_head, 0xFF, sizeof(last_head));
    heads = (GammodHead *)Mem_Alloc(sizeof(GammodHead) * (*count == 0 ? 1 : *count));
    if (heads == NULL)
        return false;

    qsort(notes, *count, sizeof(Note), note_compare);
    for (i = 0; i < *count; ++i) {
        Note *note = &notes[i];
        u8 side = (note->type & NOTE_FLAG_OPPONENT) ? 1 : 0;
        u8 lane = note->type & 3;
        if (note->type & NOTE_FLAG_SUSTAIN) {
            s32 index = last_head[side][lane];
            if (index >= 0)
                heads[index].had_sustain = true;
            continue;
        }
        heads[head_count].note = *note;
        heads[head_count].note.type &= (u8)~(NOTE_FLAG_HIT | NOTE_FLAG_SUSTAIN | NOTE_FLAG_SUSTAIN_END);
        heads[head_count].had_sustain = false;
        last_head[side][lane] = (s32)head_count;
        ++head_count;
    }

    for (i = 0; i < head_count; ++i) {
        size_t j;
        GammodHead *head = &heads[i];
        boolean fill;
        u16 end_pos = head->note.pos;
        u16 bpm;
        u16 margin_units;
        u32 p;

        if (out >= capacity) {
            Mem_Free(heads);
            return false;
        }
        notes[out++] = head->note;

        if (runtime->config.long_notes == GAMMOD_LONG_NONE ||
            (head->note.type & NOTE_FLAG_MINE))
            continue;

        fill = runtime->config.long_notes == GAMMOD_LONG_ALL ||
            (runtime->config.long_notes == GAMMOD_LONG_INVERTED && !head->had_sustain);
        if (!fill)
            continue;

        for (j = i + 1; j < head_count; ++j) {
            if (same_lane_side(&head->note, &heads[j].note)) {
                end_pos = heads[j].note.pos;
                break;
            }
        }
        if (end_pos <= head->note.pos)
            continue;

        bpm = bpm_for_pos(game, head->note.pos);
        margin_units = (u16)(((u32)bpm * GAMMOD_NOTE_MARGIN_MS * 48u + 30000u) / 60000u);
        if (margin_units < 1) margin_units = 1;
        if ((u32)head->note.pos + 12u + margin_units >= end_pos)
            continue;

        for (p = (u32)head->note.pos + 12u; p + margin_units < end_pos; p += 12u) {
            Note sustain;
            if (out >= capacity) {
                Mem_Free(heads);
                return false;
            }
            sustain.pos = (u16)p;
            sustain.type = (head->note.type & (NOTE_FLAG_OPPONENT | NOTE_FLAG_ALT_ANIM | 3)) |
                NOTE_FLAG_SUSTAIN;
            sustain.pad = head->note.pad;
            notes[out++] = sustain;
        }
        if (out > 0 && (notes[out - 1].type & NOTE_FLAG_SUSTAIN) &&
            same_lane_side(&head->note, &notes[out - 1]))
            notes[out - 1].type |= NOTE_FLAG_SUSTAIN_END;
    }

    Mem_Free(heads);
    *count = out;
    return true;
}

void Gammod_Defaults(GammodConfig *config)
{
    if (config == NULL)
        return;
    memset(config, 0, sizeof(*config));
    config->autoplay = GAMMOD_AUTOPLAY_DISABLED;
    config->long_notes = GAMMOD_LONG_NORMAL;
    config->note_placement = GAMMOD_PLACEMENT_NORMAL;
    config->perfect_only = GAMMOD_PERFECT_DISABLED;
    config->player_side = GAMMOD_SIDE_NORMAL;
    config->skip_silence = GAMMOD_SKIP_SILENCE_DISABLED;
    config->scroll_velocities = true;
    config->custom_scroll_speed_enabled = false;
    config->custom_scroll_speed = 2.0f;
    config->custom_opponent_scroll_speed = 2.0f;
    config->custom_scroll_opponent_separate = false;
    config->custom_scroll_as_multiplier = false;
    config->health_drain = 0.0f;
    config->health_gain = 1.0f;
    config->health_loss = 1.0f;
    config->playback_rate = 1.0f;
    config->skip_countdown_delay = 0.5f;
    config->starting_health_percent = 50;
    config->sick_window_ms = 45;
    config->good_window_ms = 90;
    config->bad_window_ms = 135;
    config->shit_window_ms = 160;
    config->skip_safety_beats = 1;
    config->skip_count_enemy_notes = true;
    config->perfect_fail_on_ghost = true;
    config->autoplay_act_like_opponent = true;
    config->playback_stage_rate = true;
    config->playback_match_event_durations = true;
    config->playback_match_scroll_speed = false;
}

void Gammod_LoadSave(GammodConfig *config, const FunkinSaveData *save)
{
    int flags;
    int misc;

    Gammod_Defaults(config);
    if (config == NULL || save == NULL || save->gammod_values[GMS_MARKER] != GAMMOD_SAVE_MARKER)
        return;

    config->autoplay = (GammodAutoPlay)save->gammod_values[GMS_AUTOPLAY];
    config->long_notes = (GammodLongNotes)save->gammod_values[GMS_LONG_NOTES];
    config->note_placement = (GammodNotePlacement)save->gammod_values[GMS_PLACEMENT];
    config->perfect_only = (GammodPerfectOnly)save->gammod_values[GMS_PERFECT];
    config->player_side = (GammodPlayerSide)save->gammod_values[GMS_SIDE];
    config->skip_silence = (GammodSkipSilence)save->gammod_values[GMS_SKIP_SILENCE];
    config->extra_notes = save->gammod_values[GMS_EXTRA] != 0;
    config->ghost_tapping = save->gammod_values[GMS_GHOST] != 0;
    config->scroll_velocities = save->gammod_values[GMS_SCROLL_VELOCITIES] != 0;
    config->custom_judgements = save->gammod_values[GMS_CUSTOM_JUDGEMENTS] != 0;
    config->custom_scroll_speed_enabled = save->gammod_values[GMS_CUSTOM_SCROLL_ENABLED] != 0;
    config->custom_scroll_speed = (float)save->gammod_values[GMS_CUSTOM_SCROLL_X10] / 10.0f;
    config->health_drain = (float)save->gammod_values[GMS_HEALTH_DRAIN_X10] / 10.0f;
    config->health_gain = (float)save->gammod_values[GMS_HEALTH_GAIN_X10] / 10.0f;
    config->health_loss = (float)save->gammod_values[GMS_HEALTH_LOSS_X10] / 10.0f;
    config->playback_rate = (float)save->gammod_values[GMS_PLAYBACK_X100] / 100.0f;
    config->reset_on_death = save->gammod_values[GMS_RESET_ON_DEATH] != 0;
    config->skip_countdown = save->gammod_values[GMS_SKIP_COUNTDOWN] != 0;
    config->starting_health_percent = (u16)save->gammod_values[GMS_STARTING_HEALTH];
    config->random_avoid_jacks = save->gammod_values[GMS_AVOID_JACKS] != 0;
    config->sick_window_ms = (u16)save->gammod_values[GMS_SICK_WINDOW];
    config->good_window_ms = (u16)save->gammod_values[GMS_GOOD_WINDOW];
    config->bad_window_ms = (u16)save->gammod_values[GMS_BAD_WINDOW];
    config->shit_window_ms = (u16)save->gammod_values[GMS_SHIT_WINDOW];
    config->skip_safety_beats = (u8)save->gammod_values[GMS_SKIP_SAFETY];
    config->skip_count_enemy_notes = save->gammod_values[GMS_COUNT_ENEMY] != 0;
    config->perfect_fail_on_ghost = save->gammod_values[GMS_PERFECT_FAIL_GHOST] != 0;
    config->autoplay_act_like_opponent = save->gammod_values[GMS_AUTOPLAY_ACT_OPP] != 0;
    flags = save->gammod_values[GMS_PLAYBACK_FLAGS];
    config->playback_stage_rate = (flags & PLAYBACK_FLAG_STAGE) != 0;
    config->playback_match_event_durations = (flags & PLAYBACK_FLAG_EVENTS) != 0;
    config->playback_match_scroll_speed = (flags & PLAYBACK_FLAG_SCROLL) != 0;

    config->custom_opponent_scroll_speed =
        (float)save->gammod_values[GMS_CUSTOM_OPP_SCROLL_X10] / 10.0f;
    misc = save->gammod_values[GMS_MISC_FLAGS];
    config->custom_scroll_opponent_separate = (misc & MISC_FLAG_OPP_SEPARATE) != 0;
    config->custom_scroll_as_multiplier = (misc & MISC_FLAG_SCROLL_MULT) != 0;
    config->skip_countdown_delay =
        (float)((misc & MISC_COUNTDOWN_MASK) >> MISC_COUNTDOWN_SHIFT) / 10.0f;
}

void Gammod_StoreSave(const GammodConfig *config, FunkinSaveData *save)
{
    int flags = 0;
    int misc = 0;
    int delay_tenths;
    if (config == NULL || save == NULL)
        return;
    save->gammod_values[GMS_AUTOPLAY] = config->autoplay;
    save->gammod_values[GMS_LONG_NOTES] = config->long_notes;
    save->gammod_values[GMS_PLACEMENT] = config->note_placement;
    save->gammod_values[GMS_PERFECT] = config->perfect_only;
    save->gammod_values[GMS_SIDE] = config->player_side;
    save->gammod_values[GMS_SKIP_SILENCE] = config->skip_silence;
    save->gammod_values[GMS_EXTRA] = config->extra_notes;
    save->gammod_values[GMS_GHOST] = config->ghost_tapping;
    save->gammod_values[GMS_SCROLL_VELOCITIES] = config->scroll_velocities;
    save->gammod_values[GMS_CUSTOM_JUDGEMENTS] = config->custom_judgements;
    save->gammod_values[GMS_CUSTOM_SCROLL_ENABLED] = config->custom_scroll_speed_enabled;
    save->gammod_values[GMS_CUSTOM_SCROLL_X10] = (s16)(config->custom_scroll_speed * 10.0f + 0.5f);
    save->gammod_values[GMS_HEALTH_DRAIN_X10] = (s16)(config->health_drain * 10.0f + 0.5f);
    save->gammod_values[GMS_HEALTH_GAIN_X10] = (s16)(config->health_gain * 10.0f + 0.5f);
    save->gammod_values[GMS_HEALTH_LOSS_X10] = (s16)(config->health_loss * 10.0f + 0.5f);
    save->gammod_values[GMS_PLAYBACK_X100] = (s16)(config->playback_rate * 100.0f + 0.5f);
    save->gammod_values[GMS_RESET_ON_DEATH] = config->reset_on_death;
    save->gammod_values[GMS_SKIP_COUNTDOWN] = config->skip_countdown;
    save->gammod_values[GMS_STARTING_HEALTH] = (s16)config->starting_health_percent;
    save->gammod_values[GMS_AVOID_JACKS] = config->random_avoid_jacks;
    save->gammod_values[GMS_SICK_WINDOW] = (s16)config->sick_window_ms;
    save->gammod_values[GMS_GOOD_WINDOW] = (s16)config->good_window_ms;
    save->gammod_values[GMS_BAD_WINDOW] = (s16)config->bad_window_ms;
    save->gammod_values[GMS_SHIT_WINDOW] = (s16)config->shit_window_ms;
    save->gammod_values[GMS_SKIP_SAFETY] = config->skip_safety_beats;
    save->gammod_values[GMS_COUNT_ENEMY] = config->skip_count_enemy_notes;
    save->gammod_values[GMS_PERFECT_FAIL_GHOST] = config->perfect_fail_on_ghost;
    save->gammod_values[GMS_AUTOPLAY_ACT_OPP] = config->autoplay_act_like_opponent;
    if (config->playback_stage_rate) flags |= PLAYBACK_FLAG_STAGE;
    if (config->playback_match_event_durations) flags |= PLAYBACK_FLAG_EVENTS;
    if (config->playback_match_scroll_speed) flags |= PLAYBACK_FLAG_SCROLL;
    save->gammod_values[GMS_PLAYBACK_FLAGS] = (s16)flags;

    save->gammod_values[GMS_CUSTOM_OPP_SCROLL_X10] =
        (s16)(config->custom_opponent_scroll_speed * 10.0f + 0.5f);
    if (config->custom_scroll_opponent_separate) misc |= MISC_FLAG_OPP_SEPARATE;
    if (config->custom_scroll_as_multiplier) misc |= MISC_FLAG_SCROLL_MULT;
    delay_tenths = (int)(gammod_clampf(config->skip_countdown_delay, 0.0f, 2.0f) * 10.0f + 0.5f);
    misc |= (delay_tenths << MISC_COUNTDOWN_SHIFT) & MISC_COUNTDOWN_MASK;
    save->gammod_values[GMS_MISC_FLAGS] = (s16)misc;
    save->gammod_values[GMS_MARKER] = GAMMOD_SAVE_MARKER;
}

void Gammod_Init(GammodRuntime *runtime, const GammodConfig *config)
{
    if (runtime == NULL)
        return;
    memset(runtime, 0, sizeof(*runtime));
    if (config != NULL)
        runtime->config = *config;
    else
        Gammod_Defaults(&runtime->config);
}

void Gammod_FreeChart(GammodRuntime *runtime)
{
    if (runtime == NULL)
        return;
    if (runtime->transformed_notes != NULL)
        Mem_Free(runtime->transformed_notes);
    runtime->transformed_notes = NULL;
    runtime->transformed_count = 0;
    runtime->transformed = false;
    runtime->intro_skip_pending = false;
    runtime->intro_skip_time = 0;
    runtime->intro_skip_scroll = 0;
}

static void gammod_configure_timing(GammodRuntime *runtime, GameplayState *game)
{
    float rate_float;
    fixed_t rate;
    fixed_t base_speed;
    fixed_t player_speed;
    fixed_t opponent_speed;
    fixed_t factor;

    rate_float = gammod_clampf(runtime->config.playback_rate, 0.5f, 3.0f);
    runtime->config.playback_rate = rate_float;
    rate = gammod_float_fixed(rate_float);
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
        gammod_float_fixed(gammod_clampf(runtime->config.health_gain, 0.0f, 66.0f)),
        gammod_float_fixed(gammod_clampf(runtime->config.health_loss, 0.0f, 25.0f)));

    game->block_scroll_events = !runtime->config.scroll_velocities;
    game->event_time_scale = runtime->config.playback_match_event_durations
        ? rate : FIXED_DEC(1, 1);

    base_speed = game->rhythm.speed;
    player_speed = base_speed;
    opponent_speed = base_speed;
    factor = runtime->config.playback_match_scroll_speed
        ? rate : FIXED_DEC(1, 1);

    if (runtime->config.custom_scroll_speed_enabled) {
        fixed_t player_value = gammod_float_fixed(
            gammod_clampf(runtime->config.custom_scroll_speed, 0.1f, 20.0f));
        fixed_t opponent_value = runtime->config.custom_scroll_opponent_separate
            ? gammod_float_fixed(gammod_clampf(
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

static void gammod_prepare_intro_skip(GammodRuntime *runtime, const GameplayState *game)
{
    const ChartView *chart;
    size_t i;
    u16 first_pos = 0;
    u32 safety_units;
    u16 target;

    runtime->intro_skip_pending = false;
    if (runtime->config.skip_silence != GAMMOD_SKIP_SILENCE_INTRO ||
        game == NULL || !game->loaded)
        return;

    chart = &game->chart.view;
    for (i = 0; i < chart->note_count; ++i) {
        const Note *note = &chart->notes[i];
        if (note->pos == 0xFFFFu || (note->type & (NOTE_FLAG_HIT | NOTE_FLAG_SUSTAIN)))
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
    runtime->intro_skip_time = chart_time_for_pos(game, target);
    runtime->intro_skip_pending = runtime->intro_skip_time > 0;
}

boolean Gammod_TransformChart(GammodRuntime *runtime, GameplayState *game)
{
    ChartView *chart;
    size_t capacity;
    size_t count;
    Note *notes;

    if (runtime == NULL || game == NULL || !game->loaded)
        return false;
    Gammod_FreeChart(runtime);
    chart = &game->chart.view;
    capacity = transform_capacity(chart);
    if (capacity == 0)
        return false;
    notes = (Note *)Mem_Alloc(capacity * sizeof(Note));
    if (notes == NULL)
        return false;
    memcpy(notes, chart->notes, chart->note_count * sizeof(Note));
    count = chart->note_count;

    transform_note_placement(notes, count, runtime->config.note_placement,
        runtime->config.random_avoid_jacks);
    if (!transform_player_side(notes, &count, capacity, runtime->config.player_side))
        goto fail;
    if (runtime->config.extra_notes && !transform_extra_notes(notes, &count, capacity))
        goto fail;
    if (!transform_long_notes(runtime, game, notes, &count, capacity))
        goto fail;

    qsort(notes, count, sizeof(Note), note_compare);
    chart->notes = notes;
    chart->note_count = count;
    runtime->transformed_notes = notes;
    runtime->transformed_count = count;
    runtime->transformed = true;

    game->rhythm.ghost = runtime->config.ghost_tapping;
    gammod_configure_timing(runtime, game);

    if (runtime->config.skip_countdown) {
        Gameplay_SetCountdownDelay(
            game,
            gammod_float_fixed(gammod_clampf(
                runtime->config.skip_countdown_delay, 0.0f, 2.0f)));
    }
    gammod_prepare_intro_skip(runtime, game);
    return true;

fail:
    Mem_Free(notes);
    return false;
}

void Gammod_ApplyStartingHealth(GammodRuntime *runtime, GameplayState *game)
{
    u32 percent;
    s32 health;
    if (runtime == NULL || game == NULL)
        return;
    percent = runtime->config.starting_health_percent;
    if (percent > 100u) percent = 100u;
    if (percent == 50u)
        return;
    health = (s32)(percent * 20000u / 100u);
    if (health < 800) health = 800;
    if (health > 20000) health = 20000;
    game->rhythm.health = (s16)health;
}

void Gammod_PreparePad(
    GammodRuntime *runtime,
    const GameplayState *game,
    const Pad *physical,
    Pad *effective)
{
    const ChartView *chart;
    size_t i;

    if (effective == NULL)
        return;
    if (physical != NULL)
        *effective = *physical;
    else
        memset(effective, 0, sizeof(*effective));

    if (runtime == NULL || game == NULL || !game->loaded ||
        runtime->config.autoplay == GAMMOD_AUTOPLAY_DISABLED)
        return;

    chart = &game->chart.view;
    for (i = game->first_note; i < chart->note_count; ++i) {
        const Note *note = &chart->notes[i];
        fixed_t note_pos = (fixed_t)note->pos << FIXED_SHIFT;
        fixed_t delta = note_pos - game->note_scroll;
        u16 button;

        if (note->type & (NOTE_FLAG_HIT | NOTE_FLAG_OPPONENT | NOTE_FLAG_MINE))
            continue;
        if (delta > game->rhythm.early_safe)
            break;
        if (delta < -game->rhythm.late_sus_safe)
            continue;
        button = gammod_lane_button(note->type & 3);
        effective->held |= button;
        if (!(note->type & NOTE_FLAG_SUSTAIN) && delta <= 0)
            effective->press |= button;
    }
}

static boolean gammod_opponent_tap_this_frame(const GameplayState *game, u8 lane)
{
    const ChartView *chart;
    size_t i;
    s32 current;

    if (game == NULL || !game->loaded)
        return false;
    chart = &game->chart.view;
    current = game->note_scroll >> FIXED_SHIFT;
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

static boolean gammod_opponent_hold_active(const GameplayState *game)
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
                !(note->type & NOTE_FLAG_SUSTAIN) || (note->type & 3) != lane)
                continue;
            delta = current - (s32)note->pos;
            if (delta < 0 || delta > 16)
                continue;
            if (latest == NULL || note->pos > latest->pos)
                latest = note;
        }
        if (latest != NULL && !(latest->type & NOTE_FLAG_SUSTAIN_END))
            return true;
    }
    return false;
}

static void gammod_drain_nonlethal(GameplayState *game, s32 amount)
{
    if (game == NULL || amount <= 0 || game->rhythm.health <= GAMMOD_DRAIN_FLOOR)
        return;
    game->rhythm.health -= amount;
    if (game->rhythm.health < GAMMOD_DRAIN_FLOOR)
        game->rhythm.health = GAMMOD_DRAIN_FLOOR;
}

static void gammod_apply_health_drain(
    GammodRuntime *runtime,
    GameplayState *game,
    fixed_t elapsed)
{
    u8 mask;
    int lane;
    float tap_drain;
    float seconds;

    if (runtime->config.health_drain <= 0.0f)
        return;
    mask = game->events.opponent_hit_mask;
    tap_drain = runtime->config.health_drain == 66.0f
        ? 100.0f : runtime->config.health_drain;
    for (lane = 0; lane < 4; ++lane) {
        if ((mask & (1u << lane)) && gammod_opponent_tap_this_frame(game, (u8)lane)) {
            s32 amount = (s32)(300.0f * tap_drain + 0.5f);
            gammod_drain_nonlethal(game, amount);
        }
    }

    if (gammod_opponent_hold_active(game)) {
        seconds = (float)elapsed / (float)FIXED_UNIT;
        gammod_drain_nonlethal(
            game,
            (s32)(runtime->config.health_drain *
                (float)GAMMOD_HOLD_DRAIN_UNITS_SEC * seconds + 0.5f));
    }
}

void Gammod_OnGameplayFrame(GammodRuntime *runtime, GameplayState *game, fixed_t elapsed)
{
    if (runtime == NULL || game == NULL || !game->loaded)
        return;

    if (runtime->intro_skip_pending && game->audio_started) {
        if (Gameplay_SeekIntro(
                game,
                runtime->intro_skip_time,
                runtime->intro_skip_scroll)) {
            runtime->intro_skip_pending = false;
            return;
        }
        runtime->intro_skip_pending = false;
    }

    gammod_apply_health_drain(runtime, game, elapsed);

    if (runtime->config.perfect_only != GAMMOD_PERFECT_DISABLED) {
        boolean bad_judgement = false;
        if (game->events.mine_hit)
            bad_judgement = true;
        if (game->events.player_missed) {
            if (!game->events.empty_press_miss || runtime->config.perfect_fail_on_ghost)
                bad_judgement = true;
        }
        if (game->events.player_hit_mask != 0) {
            if (runtime->config.perfect_only == GAMMOD_PERFECT_GOLDEN)
                bad_judgement = game->events.last_rating != HIT_SICK;
            else
                bad_judgement = game->events.last_rating == HIT_BAD ||
                    game->events.last_rating == HIT_SHIT;
        }
        if (bad_judgement) {
            runtime->perfect_failed = true;
            game->rhythm.health = 0;
        }
    }
}

boolean Gammod_ShouldSkipCountdown(const GammodRuntime *runtime)
{
    return runtime != NULL && runtime->config.skip_countdown;
}

boolean Gammod_ResetOnDeath(const GammodRuntime *runtime)
{
    return runtime != NULL && runtime->config.reset_on_death;
}

boolean Gammod_PerfectFailed(const GammodRuntime *runtime)
{
    return runtime != NULL && runtime->perfect_failed;
}

fixed_t Gammod_PlaybackRate(const GammodRuntime *runtime)
{
    if (runtime == NULL)
        return FIXED_DEC(1, 1);
    return gammod_float_fixed(gammod_clampf(runtime->config.playback_rate, 0.5f, 3.0f));
}

fixed_t Gammod_PresentationDelta(const GammodRuntime *runtime, fixed_t elapsed)
{
    if (runtime == NULL || !runtime->config.playback_stage_rate)
        return elapsed;
    return FIXED_MUL(elapsed, Gammod_PlaybackRate(runtime));
}
