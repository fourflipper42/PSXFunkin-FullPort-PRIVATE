#include "note_kind_runtime.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static boolean note_kind_path(
    char *out,
    size_t out_size,
    const char *chart_path)
{
    const char *version;
    const char *dot;
    size_t stem_len;
    int written;

    if (out == NULL || out_size == 0 || chart_path == NULL)
        return false;
    version = strstr(chart_path, ";1");
    dot = strrchr(chart_path, '.');
    if (dot == NULL || (version != NULL && dot > version))
        return false;
    stem_len = (size_t)(dot - chart_path);
    written = snprintf(out, out_size, "%.*s.FKND%s",
        (int)stem_len, chart_path, version != NULL ? ";1" : "");
    return written >= 0 && (size_t)written < out_size;
}

void NoteKindRuntime_Init(NoteKindRuntime *runtime)
{
    int lane;
    if (runtime == NULL)
        return;
    memset(runtime, 0, sizeof(*runtime));
    for (lane = 0; lane < 4; ++lane) {
        runtime->last_player_pos[lane] = 0xFFFFu;
        runtime->last_opponent_pos[lane] = 0xFFFFu;
    }
}

boolean NoteKindRuntime_LoadForChart(
    NoteKindRuntime *runtime,
    const char *chart_path)
{
    char path[320];
    if (runtime == NULL || chart_path == NULL)
        return false;
    NoteKindRuntime_Free(runtime);
    NoteKindRuntime_Init(runtime);
    if (!note_kind_path(path, sizeof(path), chart_path))
        return false;
    runtime->loaded = NoteKinds_Load(&runtime->table, path);
    if (runtime->loaded)
        printf("[PS2] note kinds loaded: %u\n", (unsigned)runtime->table.count);
    return runtime->loaded;
}

void NoteKindRuntime_Free(NoteKindRuntime *runtime)
{
    if (runtime == NULL)
        return;
    NoteKinds_Free(&runtime->table);
    memset(runtime, 0, sizeof(*runtime));
}

static boolean resolve_lane_hit(
    NoteKindHit *out,
    const GameplayState *game,
    u8 lane,
    boolean opponent,
    u16 *last_pos)
{
    const ChartView *chart;
    const Note *best = NULL;
    s32 best_distance = 0x7FFFFFFF;
    s32 current;
    size_t i;

    if (out == NULL || game == NULL || !game->loaded || last_pos == NULL)
        return false;
    memset(out, 0, sizeof(*out));
    chart = &game->chart.view;
    current = game->note_scroll >> FIXED_SHIFT;

    /* Search newly-hit notes around the exact conductor position. Taps are
     * normally within the judgement window, while opponent auto-hits land at
     * or immediately before the current scroll. Sustain pieces are generated
     * every 12 units and therefore still resolve unambiguously per lane. */
    for (i = 0; i < chart->note_count; ++i) {
        const Note *note = &chart->notes[i];
        s32 distance;
        boolean note_opponent;
        if (!(note->type & NOTE_FLAG_HIT) || (note->type & 3) != (lane & 3))
            continue;
        note_opponent = (note->type & NOTE_FLAG_OPPONENT) != 0;
        if (note_opponent != opponent || note->pos == *last_pos)
            continue;
        distance = abs((s32)note->pos - current);
        if (distance > 24)
            continue;
        if (distance < best_distance ||
            (distance == best_distance && best != NULL && note->pos > best->pos)) {
            best = note;
            best_distance = distance;
        }
    }

    if (best == NULL)
        return false;
    out->kind_index = best->pad;
    out->note_type = best->type;
    out->lane = lane & 3;
    out->valid = true;
    *last_pos = best->pos;
    return true;
}

void NoteKindRuntime_ResolveFrame(
    NoteKindRuntime *runtime,
    const GameplayState *game)
{
    int lane;
    if (runtime == NULL || game == NULL)
        return;
    memset(runtime->player, 0, sizeof(runtime->player));
    memset(runtime->opponent, 0, sizeof(runtime->opponent));

    for (lane = 0; lane < 4; ++lane) {
        if (game->events.player_hit_mask & (1u << lane))
            resolve_lane_hit(&runtime->player[lane], game, (u8)lane, false,
                &runtime->last_player_pos[lane]);
        if (game->events.opponent_hit_mask & (1u << lane))
            resolve_lane_hit(&runtime->opponent[lane], game, (u8)lane, true,
                &runtime->last_opponent_pos[lane]);
    }
}

static const char *base_animation(u8 lane)
{
    static const char *names[4] = {
        "singLEFT", "singDOWN", "singUP", "singRIGHT"
    };
    return names[lane & 3];
}

static boolean try_animation(
    Character *character,
    const char *base,
    const char *suffix,
    boolean sustain,
    boolean restart)
{
    char name[128];
    if (character == NULL || !character->loaded || base == NULL)
        return false;

    if (suffix != NULL && suffix[0] != '\0') {
        if (sustain) {
            snprintf(name, sizeof(name), "%s-%s-hold", base, suffix);
            if (Character_HasAnimation(character, name))
                return Character_Play(character, name, restart);
        }
        snprintf(name, sizeof(name), "%s-%s", base, suffix);
        if (Character_HasAnimation(character, name))
            return Character_Play(character, name, restart);
    }
    if (sustain) {
        snprintf(name, sizeof(name), "%s-hold", base);
        if (Character_HasAnimation(character, name))
            return Character_Play(character, name, restart);
    }
    return Character_Play(character, base, restart);
}

boolean NoteKindRuntime_PlayLaneAnimation(
    NoteKindRuntime *runtime,
    Character *character,
    const NoteKindHit *hit,
    boolean force_restart)
{
    const char *base;
    char suffix[80];
    boolean sustain;

    if (character == NULL || hit == NULL || !hit->valid)
        return false;
    base = base_animation(hit->lane);
    sustain = (hit->note_type & NOTE_FLAG_SUSTAIN) != 0;

    if (runtime != NULL && runtime->loaded && hit->kind_index != 0) {
        if (NoteKinds_NameEquals(&runtime->table, hit->kind_index, "noanim"))
            return true; /* Handled by intentionally doing nothing. */
        if (NoteKinds_NameEquals(&runtime->table, hit->kind_index, "uniSuffix")) {
            suffix[0] = '\0';
            if (NoteKinds_ParamString(
                &runtime->table,
                hit->kind_index,
                "customSuffix",
                suffix,
                sizeof(suffix))) {
                return try_animation(character, base, suffix, sustain, force_restart);
            }
        }
    }
    return try_animation(character, base, NULL, sustain, force_restart);
}
