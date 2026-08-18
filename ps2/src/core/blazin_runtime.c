#include "blazin_runtime.h"

#include "mem.h"
#include "presentation_registry.h"
#include "random.h"
#include <stdio.h>
#include <string.h>

static boolean g_active;
static u8 *g_processed;
static size_t g_processed_count;
static fixed_t g_last_scroll;
static boolean g_player_alt;
static boolean g_opponent_alt;
static boolean g_player_cant_uppercut;
static boolean g_opponent_cant_uppercut;

static boolean begins(const char *text, const char *prefix)
{
    size_t n;
    if (text == NULL || prefix == NULL)
        return false;
    n = strlen(prefix);
    return strncmp(text, prefix, n) == 0;
}

static boolean contains(const char *text, const char *needle)
{
    return text != NULL && needle != NULL && strstr(text, needle) != NULL;
}

static void play(Character *character, const char *name)
{
    if (character == NULL || !character->loaded || name == NULL)
        return;
    if (Character_HasAnimation(character, name))
        Character_Play(character, name, true);
}

static void idle(Character *character)
{
    if (character == NULL || !character->loaded)
        return;
    if (Character_HasAnimation(character, "idle"))
        Character_Play(character, "idle", true);
    else
        Character_Dance(character, true);
}

static void punch(Character *character, boolean high, boolean *alternate)
{
    char name[20];
    if (alternate == NULL)
        return;
    *alternate = !*alternate;
    snprintf(name, sizeof(name), "%s%d",
        high ? "punchHigh" : "punchLow",
        *alternate ? 1 : 2);
    if (character != NULL && Character_HasAnimation(character, name))
        Character_Play(character, name, true);
    else
        play(character, high ? "punchHigh" : "punchLow");
}

static void player_hit_reaction(Character *player, const char *kind)
{
    if (contains(kind, "spin"))
        play(player, "hitSpin");
    else if (contains(kind, "low"))
        play(player, "hitLow");
    else
        play(player, "hitHigh");
}

static void opponent_attack(Character *opponent, const char *kind)
{
    punch(opponent, !contains(kind, "low"), &g_opponent_alt);
}

static void success_pair(Character *player, Character *opponent, const char *kind)
{
    if (g_player_cant_uppercut) {
        play(player, "block");
        g_player_cant_uppercut = false;
    }
    if (g_opponent_cant_uppercut) {
        punch(opponent, true, &g_opponent_alt);
        g_opponent_cant_uppercut = false;
    }

    if (begins(kind, "weekend-1-punchlow")) {
        punch(player, false, &g_player_alt);
        if (contains(kind, "blocked")) play(opponent, "block");
        else if (contains(kind, "dodged")) play(opponent, "dodge");
        else if (contains(kind, "spin")) play(opponent, "hitSpin");
        else play(opponent, "hitLow");
        return;
    }
    if (begins(kind, "weekend-1-punchhigh")) {
        punch(player, true, &g_player_alt);
        if (contains(kind, "blocked")) play(opponent, "block");
        else if (contains(kind, "dodged")) play(opponent, "dodge");
        else if (contains(kind, "spin")) play(opponent, "hitSpin");
        else play(opponent, "hitHigh");
        return;
    }
    if (begins(kind, "weekend-1-block")) {
        play(player, "block");
        opponent_attack(opponent, kind);
        return;
    }
    if (begins(kind, "weekend-1-dodge")) {
        play(player, "dodge");
        opponent_attack(opponent, kind);
        return;
    }
    if (begins(kind, "weekend-1-hit")) {
        player_hit_reaction(player, kind);
        opponent_attack(opponent, kind);
        return;
    }
    if (strcmp(kind, "weekend-1-picouppercutprep") == 0) {
        play(player, "uppercutPrep");
        return;
    }
    if (strcmp(kind, "weekend-1-picouppercut") == 0) {
        play(player, "uppercut");
        play(opponent, "uppercutHit");
        return;
    }
    if (strcmp(kind, "weekend-1-darnelluppercutprep") == 0) {
        idle(player);
        play(opponent, "uppercutPrep");
        return;
    }
    if (strcmp(kind, "weekend-1-darnelluppercut") == 0) {
        play(player, "uppercutHit");
        play(opponent, "uppercut");
        return;
    }
    if (strcmp(kind, "weekend-1-idle") == 0) {
        idle(player);
        idle(opponent);
        return;
    }
    if (strcmp(kind, "weekend-1-fakeout") == 0) {
        play(player, "fakeout");
        play(opponent, "cringe");
        return;
    }
    if (strcmp(kind, "weekend-1-taunt") == 0) {
        const char *p = Character_CurrentAnimationName(player);
        const char *o = Character_CurrentAnimationName(opponent);
        if (p != NULL && strcmp(p, "fakeout") == 0) play(player, "taunt");
        else idle(player);
        if (o != NULL && strcmp(o, "cringe") == 0) play(opponent, "pissed");
        else idle(opponent);
        return;
    }
    if (strcmp(kind, "weekend-1-tauntforce") == 0) {
        play(player, "taunt");
        play(opponent, "pissed");
        return;
    }
    if (strcmp(kind, "weekend-1-reversefakeout") == 0) {
        idle(player);
        play(opponent, "fakeout");
    }
}

static void miss_pair(Character *player, Character *opponent, const char *kind)
{
    if (begins(kind, "weekend-1-punch") ||
        begins(kind, "weekend-1-block") ||
        begins(kind, "weekend-1-dodge") ||
        begins(kind, "weekend-1-hit")) {
        player_hit_reaction(player, kind);
        opponent_attack(opponent, kind);
        return;
    }
    if (strcmp(kind, "weekend-1-picouppercutprep") == 0) {
        punch(player, true, &g_player_alt);
        play(opponent, "hitHigh");
        g_player_cant_uppercut = true;
        g_opponent_cant_uppercut = true;
        return;
    }
    if (strcmp(kind, "weekend-1-picouppercut") == 0) {
        play(player, "uppercut");
        if (g_opponent_cant_uppercut)
            punch(opponent, true, &g_opponent_alt);
        else
            play(opponent, "dodge");
        g_opponent_cant_uppercut = false;
        return;
    }
    if (strcmp(kind, "weekend-1-darnelluppercutprep") == 0) {
        idle(player);
        play(opponent, "uppercutPrep");
        return;
    }
    if (strcmp(kind, "weekend-1-darnelluppercut") == 0) {
        play(player, "uppercutHit");
        play(opponent, "uppercut");
        return;
    }
    if (strcmp(kind, "weekend-1-idle") == 0) {
        idle(player);
        idle(opponent);
        return;
    }
    if (strcmp(kind, "weekend-1-fakeout") == 0) {
        play(player, "hitHigh");
        play(opponent, "cringe");
        return;
    }
    if (strcmp(kind, "weekend-1-taunt") == 0 ||
        strcmp(kind, "weekend-1-tauntforce") == 0) {
        success_pair(player, opponent, kind);
        return;
    }
    if (strcmp(kind, "weekend-1-reversefakeout") == 0) {
        idle(player);
        play(opponent, "fakeout");
    }
}

static void reset_attempt(void)
{
    if (g_processed != NULL && g_processed_count != 0)
        memset(g_processed, 0, g_processed_count);
    g_player_alt = false;
    g_opponent_alt = false;
    g_player_cant_uppercut = false;
    g_opponent_cant_uppercut = false;
}

void BlazinRuntime_End(void)
{
    if (g_processed != NULL)
        Mem_Free(g_processed);
    g_processed = NULL;
    g_processed_count = 0;
    g_active = false;
    g_last_scroll = 0;
    reset_attempt();
}

void BlazinRuntime_Begin(GameplayState *game)
{
    BlazinRuntime_End();
    if (game == NULL || !game->loaded)
        return;

    g_active = true;
    g_processed_count = game->chart.view.note_count;
    if (g_processed_count != 0) {
        g_processed = (u8 *)Mem_Alloc(g_processed_count);
        if (g_processed != NULL)
            memset(g_processed, 0, g_processed_count);
        else
            g_processed_count = 0;
    }
    g_last_scroll = game->note_scroll;
}

void BlazinRuntime_Tick(
    GameplayState *game,
    const NoteKindRuntime *note_kinds)
{
    ChartView *chart;
    Character *player;
    Character *opponent;
    size_t i;

    if (!g_active || game == NULL || !game->loaded ||
        note_kinds == NULL || !note_kinds->loaded)
        return;

    if (game->note_scroll + (48 << FIXED_SHIFT) < g_last_scroll)
        reset_attempt();
    g_last_scroll = game->note_scroll;

    player = PresentationRegistry_Player();
    opponent = PresentationRegistry_Opponent();
    chart = &game->chart.view;

    if (game->events.empty_press_miss) {
        if (game->rhythm.health <= 1000) {
            play(player, "hitLow");
            punch(opponent, false, &g_opponent_alt);
        } else {
            punch(player, true, &g_player_alt);
            play(opponent, RandomRange(0, 1) == 0 ? "dodge" : "block");
        }
    }

    for (i = 0; i < chart->note_count; ++i) {
        Note *note = &chart->notes[i];
        NoteKindEntry entry;
        fixed_t fp;
        fixed_t safe;
        boolean opponent_note;
        boolean missed;

        if (!(note->type & NOTE_FLAG_HIT) || (note->type & NOTE_FLAG_SUSTAIN))
            continue;
        if (g_processed != NULL && i < g_processed_count && g_processed[i])
            continue;
        if (!NoteKinds_Get(&note_kinds->table, note->pad, &entry) ||
            entry.name == NULL || !begins(entry.name, "weekend-1-"))
            continue;

        opponent_note = (note->type & NOTE_FLAG_OPPONENT) != 0;
        fp = (fixed_t)note->pos << FIXED_SHIFT;
        safe = game->rhythm.late_safe;
        missed = !opponent_note && fp + safe < game->note_scroll;

        if (!missed && !opponent_note &&
            (game->events.last_rating == HIT_BAD || game->events.last_rating == HIT_SHIT) &&
            game->rhythm.health <= 6000 && RandomRange(0, 99) < 30) {
            punch(player, true, &g_player_alt);
            play(opponent, "uppercutPrep");
        } else if (missed) {
            miss_pair(player, opponent, entry.name);
        } else {
            success_pair(player, opponent, entry.name);
        }

        if (g_processed != NULL && i < g_processed_count)
            g_processed[i] = 1;
    }
}
