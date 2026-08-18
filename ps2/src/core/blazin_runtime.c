#include "blazin_runtime.h"

#include "mem.h"
#include "presentation_registry.h"
#include "random.h"
#include <string.h>

static boolean g_active;
static u8 *g_processed;
static size_t g_processed_count;
static fixed_t g_last_scroll;
static boolean g_player_alt;
static boolean g_opponent_alt;
static boolean g_player_cant_uppercut;
static boolean g_opponent_cant_uppercut;

static boolean starts_with(const char *text, const char *prefix)
{
    size_t n;
    if (text == NULL || prefix == NULL)
        return false;
    n = strlen(prefix);
    return strncmp(text, prefix, n) == 0;
}

static void play_if_present(Character *character, const char *name)
{
    if (character == NULL || !character->loaded || name == NULL)
        return;
    if (Character_HasAnimation(character, name))
        Character_Play(character, name, true);
}

static void play_idle(Character *character)
{
    if (character == NULL || !character->loaded)
        return;
    if (Character_HasAnimation(character, "idle"))
        Character_Play(character, "idle", true);
    else
        Character_Dance(character, true);
}

static void play_alt_punch(Character *character, boolean high, boolean *alternate)
{
    char name[16];
    if (alternate == NULL)
        return;
    *alternate = !*alternate;
    snprintf(name, sizeof(name), "%s%d",
        high ? "punchHigh" : "punchLow",
        *alternate ? 1 : 2);
    if (character != NULL && Character_HasAnimation(character, name))
        Character_Play(character, name, true);
    else
        play_if_present(character, high ? "punchHigh" : "punchLow");
}

static void player_hit_anim(const char *kind, Character *player)
{
    if (strcmp(kind, "weekend-1-punchlowspin") == 0) play_if_present(player, "hitSpin");
    else if (starts_with(kind, "weekend-1-punchlow")) play_if_present(player, "hitLow");
    else if (strcmp(kind, "weekend-1-punchhighspin") == 0) play_if_present(player, "hitSpin");
    else if (starts_with(kind, "weekend-1-punchhigh")) play_if_present(player, "hitHigh");
    else if (strcmp(kind, "weekend-1-blocklow") == 0) play_if_present(player, "hitLow");
    else if (strcmp(kind, "weekend-1-blockspin") == 0) play_if_present(player, "hitSpin");
    else if (strcmp(kind, "weekend-1-blockhigh") == 0) play_if_present(player, "hitHigh");
    else if (strcmp(kind, "weekend-1-dodgelow") == 0) play_if_present(player, "hitLow");
    else if (strcmp(kind, "weekend-1-dodgespin") == 0) play_if_present(player, "hitSpin");
    else if (strcmp(kind, "weekend-1-dodgehigh") == 0) play_if_present(player, "hitHigh");
    else if (strcmp(kind, "weekend-1-hitlow") == 0) play_if_present(player, "hitLow");
    else if (strcmp(kind, "weekend-1-hitspin") == 0) play_if_present(player, "hitSpin");
    else if (strcmp(kind, "weekend-1-hithigh") == 0) play_if_present(player, "hitHigh");
    else if (strcmp(kind, "weekend-1-picouppercutprep") == 0) {
        play_alt_punch(player, true, &g_player_alt);
        g_player_cant_uppercut = true;
    } else if (strcmp(kind, "weekend-1-picouppercut") == 0) {
        play_if_present(player, "uppercut");
    } else if (strcmp(kind, "weekend-1-darnelluppercutprep") == 0) {
        play_idle(player);
    } else if (strcmp(kind, "weekend-1-darnelluppercut") == 0) {
        play_if_present(player, "uppercutHit");
    } else if (strcmp(kind, "weekend-1-idle") == 0) {
        play_idle(player);
    } else if (strcmp(kind, "weekend-1-fakeout") == 0) {
        play_if_present(player, "hitHigh");
    } else if (strcmp(kind, "weekend-1-taunt") == 0) {
        if (strcmp(Character_CurrentAnimationName(player) != NULL ? Character_CurrentAnimationName(player) : "", "fakeout") == 0)
            play_if_present(player, "taunt");
        else
            play_idle(player);
    } else if (strcmp(kind, "weekend-1-tauntforce") == 0) {
        play_if_present(player, "taunt");
    } else if (strcmp(kind, "weekend-1-reversefakeout") == 0) {
        play_idle(player);
    }
}

static void opponent_hit_anim(const char *kind, Character *opponent)
{
    if (starts_with(kind, "weekend-1-punchlow")) play_alt_punch(opponent, false, &g_opponent_alt);
    else if (starts_with(kind, "weekend-1-punchhigh")) play_alt_punch(opponent, true, &g_opponent_alt);
    else if (strcmp(kind, "weekend-1-blocklow") == 0) play_alt_punch(opponent, false, &g_opponent_alt);
    else if (strcmp(kind, "weekend-1-blockhigh") == 0 || strcmp(kind, "weekend-1-blockspin") == 0) play_alt_punch(opponent, true, &g_opponent_alt);
    else if (strcmp(kind, "weekend-1-dodgelow") == 0) play_alt_punch(opponent, false, &g_opponent_alt);
    else if (strcmp(kind, "weekend-1-dodgehigh") == 0 || strcmp(kind, "weekend-1-dodgespin") == 0) play_alt_punch(opponent, true, &g_opponent_alt);
    else if (strcmp(kind, "weekend-1-hitlow") == 0) play_alt_punch(opponent, false, &g_opponent_alt);
    else if (strcmp(kind, "weekend-1-hithigh") == 0 || strcmp(kind, "weekend-1-hitspin") == 0) play_alt_punch(opponent, true, &g_opponent_alt);
    else if (strcmp(kind, "weekend-1-picouppercutprep") == 0) {
        play_if_present(opponent, "hitHigh");
        g_opponent_cant_uppercut = true;
    } else if (strcmp(kind, "weekend-1-picouppercut") == 0) {
        if (g_opponent_cant_uppercut)
            play_alt_punch(opponent, true, &g_opponent_alt);
        else
            play_if_present(opponent, "uppercutHit");
        g_opponent_cant_uppercut = false;
    } else if (strcmp(kind, "weekend-1-darnelluppercutprep") == 0) {
        play_if_present(opponent, "uppercutPrep");
    } else if (strcmp(kind, "weekend-1-darnelluppercut") == 0) {
        play_if_present(opponent, "uppercut");
    } else if (strcmp(kind, "weekend-1-idle") == 0) {
        play_idle(opponent);
    } else if (strcmp(kind, "weekend-1-fakeout") == 0) {
        play_if_present(opponent, "cringe");
    } else if (strcmp(kind, "weekend-1-taunt") == 0) {
        if (strcmp(Character_CurrentAnimationName(opponent) != NULL ? Character_CurrentAnimationName(opponent) : "", "cringe") == 0)
            play_if_present(opponent, "pissed");
        else
            play_idle(opponent);
    } else if (strcmp(kind, "weekend-1-tauntforce") == 0) {
        play_if_present(opponent, "pissed");
    } else if (strcmp(kind, "weekend-1-reversefakeout") == 0) {
        play_if_present(opponent, "fakeout");
    }
}

static void player_success_anim(const char *kind, Character *player)
{
    if (g_player_cant_uppercut) {
        play_if_present(player, "block");
        g_player_cant_uppercut = false;
        return;
    }

    if (starts_with(kind, "weekend-1-punchlow")) play_alt_punch(player, false, &g_player_alt);
    else if (starts_with(kind, "weekend-1-punchhigh")) play_alt_punch(player, true, &g_player_alt);
    else if (starts_with(kind, "weekend-1-block")) play_if_present(player, "block");
    else if (starts_with(kind, "weekend-1-dodge")) play_if_present(player, "dodge");
    else if (strcmp(kind, "weekend-1-hitlow") == 0) play_if_present(player, "hitLow");
    else if (strcmp(kind, "weekend-1-hitspin") == 0) play_if_present(player, "hitSpin");
    else if (strcmp(kind, "weekend-1-hithigh") == 0) play_if_present(player, "hitHigh");
    else if (strcmp(kind, "weekend-1-picouppercutprep") == 0) play_if_present(player, "uppercutPrep");
    else if (strcmp(kind, "weekend-1-picouppercut") == 0) play_if_present(player, "uppercut");
    else if (strcmp(kind, "weekend-1-darnelluppercutprep") == 0) play_idle(player);
    else if (strcmp(kind, "weekend-1-darnelluppercut") == 0) play_if_present(player, "uppercutHit");
    else if (strcmp(kind, "weekend-1-idle") == 0) play_idle(player);
    else if (strcmp(kind, "weekend-1-fakeout") == 0) play_if_present(player, "fakeout");
    else if (strcmp(kind, "weekend-1-taunt") == 0) {
        const char *cur = Character_CurrentAnimationName(player);
        if (cur != NULL && strcmp(cur, "fakeout") == 0) play_if_present(player, "taunt");
        else play_idle(player);
    } else if (strcmp(kind, "weekend-1-tauntforce") == 0) play_if_present(player, "taunt");
    else if (strcmp(kind, "weekend-1-reversefakeout") == 0) play_idle(player);
}

static void opponent_success_anim(const char *kind, Character *opponent)
{
    if (g_opponent_cant_uppercut) {
        play_alt_punch(opponent, true, &g_opponent_alt);
        g_opponent_cant_uppercut = false;
        return;
    }

    if (strcmp(kind, "weekend-1-punchlow") == 0) play_if_present(opponent, "hitLow");
    else if (strcmp(kind, "weekend-1-punchlowblocked") == 0) play_if_present(opponent, "block");
    else if (strcmp(kind, "weekend-1-punchlowdodged") == 0) play_if_present(opponent, "dodge");
    else if (strcmp(kind, "weekend-1-punchlowspin") == 0) play_if_present(opponent, "hitSpin");
    else if (strcmp(kind, "weekend-1-punchhigh") == 0) play_if_present(opponent, "hitHigh");
    else if (strcmp(kind, "weekend-1-punchhighblocked") == 0) play_if_present(opponent, "block");
    else if (strcmp(kind, "weekend-1-punchhighdodged") == 0) play_if_present(opponent, "dodge");
    else if (strcmp(kind, "weekend-1-punchhighspin") == 0) play_if_present(opponent, "hitSpin");
    else if (strcmp(kind, "weekend-1-blocklow") == 0) play_alt_punch(opponent, false, &g_opponent_alt);
    else if (strcmp(kind, "weekend-1-blockhigh") == 0 || strcmp(kind, "weekend-1-blockspin") == 0) play_alt_punch(opponent, true, &g_opponent_alt);
    else if (strcmp(kind, "weekend-1-dodgelow") == 0) play_alt_punch(opponent, false, &g_opponent_alt);
    else if (strcmp(kind, "weekend-1-dodgehigh") == 0 || strcmp(kind, "weekend-1-dodgespin") == 0) play_alt_punch(opponent, true, &g_opponent_alt);
    else if (strcmp(kind, "weekend-1-hitlow") == 0) play_alt_punch(opponent, false, &g_opponent_alt);
    else if (strcmp(kind, "weekend-1-hithigh") == 0 || strcmp(kind, "weekend-1-hitspin") == 0) play_alt_punch(opponent, true, &g_opponent_alt);
    else if (strcmp(kind, "weekend-1-picouppercut") == 0) play_if_present(opponent, "uppercutHit");
    else if (strcmp(kind, "weekend-1-darnelluppercutprep") == 0) play_if_present(opponent, "uppercutPrep");
    else if (strcmp(kind, "weekend-1-darnelluppercut") == 0) play_if_present(opponent, "uppercut");
    else if (strcmp(kind, "weekend-1-idle") == 0) play_idle(opponent);
    else if (strcmp(kind, "weekend-1-fakeout") == 0) play_if_present(opponent, "cringe");
    else if (strcmp(kind, "weekend-1-taunt") == 0) {
        const char *cur = Character_CurrentAnimationName(opponent);
        if (cur != NULL && strcmp(cur, "cringe") == 0) play_if_present(opponent, "pissed");
        else play_idle(opponent);
    } else if (strcmp(kind, "weekend-1-tauntforce") == 0) play_if_present(opponent, "pissed");
    else if (strcmp(kind, "weekend-1-reversefakeout") == 0) play_if_present(opponent, "fakeout");
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
    g_player_alt = false;
    g_opponent_alt = false;
    g_player_cant_uppercut = false;
    g_opponent_cant_uppercut = false;
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
            play_if_present(player, "hitLow");
            play_alt_punch(opponent, false, &g_opponent_alt);
        } else {
            play_alt_punch(player, true, &g_player_alt);
            if (RandomRange(0, 1) == 0) play_if_present(opponent, "dodge");
            else play_if_present(opponent, "block");
        }
    }

    for (i = 0; i < chart->note_count; ++i) {
        Note *note = &chart->notes[i];
        NoteKindEntry entry;
        boolean opponent_note;
        boolean missed;
        fixed_t fp;
        fixed_t safe;

        if (!(note->type & NOTE_FLAG_HIT) || (note->type & NOTE_FLAG_SUSTAIN))
            continue;
        if (g_processed != NULL && i < g_processed_count && g_processed[i])
            continue;
        if (!NoteKinds_Get(&note_kinds->table, note->pad, &entry) ||
            entry.name == NULL || !starts_with(entry.name, "weekend-1-"))
            continue;

        opponent_note = (note->type & NOTE_FLAG_OPPONENT) != 0;
        fp = (fixed_t)note->pos << FIXED_SHIFT;
        safe = game->rhythm.late_safe;
        missed = !opponent_note && fp + safe < game->note_scroll;

        if (!missed && !opponent_note &&
            (game->events.last_rating == HIT_BAD || game->events.last_rating == HIT_SHIT) &&
            game->rhythm.health <= 6000 && RandomRange(0, 99) < 30) {
            play_alt_punch(player, true, &g_player_alt);
            play_if_present(opponent, "uppercutPrep");
        } else if (missed) {
            player_hit_anim(entry.name, player);
            opponent_hit_anim(entry.name, opponent);
        } else {
            player_success_anim(entry.name, player);
            opponent_success_anim(entry.name, opponent);
        }

        if (g_processed != NULL && i < g_processed_count)
            g_processed[i] = 1;
    }
}
