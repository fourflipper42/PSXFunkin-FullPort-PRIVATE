#include "endless_mode.h"

#include <string.h>

void EndlessMode_Init(EndlessMode *endless, boolean enabled)
{
    if (endless == NULL)
        return;
    memset(endless, 0, sizeof(*endless));
    endless->enabled = enabled;
}

boolean EndlessMode_SongCompatible(const char *song_id, const char *variation)
{
    (void)variation;
    if (song_id == NULL)
        return false;
    /* Supplied Endless Mode 2.0.2 ships with spaghetti-* disabled. */
    return strcmp(song_id, "spaghetti") != 0;
}

void EndlessMode_SetSong(
    EndlessMode *endless,
    const char *song_id,
    const char *variation,
    boolean story_mode)
{
    boolean wanted;

    if (endless == NULL)
        return;
    wanted = endless->enabled;
    endless->incompatible = story_mode ||
        !EndlessMode_SongCompatible(song_id, variation);
    if (endless->incompatible)
        endless->enabled = false;
    endless->ending = false;
    endless->died = false;
    endless->current_loop = 0;
    endless->total_notes_hit = 0;
    endless->total_notes_played = 0;
    endless->tally_combo = 0;
    endless->tally_max_combo = 0;
    endless->carry_health = 0;
    endless->carry_score = 0;
    endless->carry_misses = 0;
    if (!endless->incompatible)
        endless->enabled = wanted;
}

void EndlessMode_Toggle(EndlessMode *endless)
{
    if (endless == NULL || endless->incompatible)
        return;
    endless->enabled = !endless->enabled;
}

void EndlessMode_OnSongStart(EndlessMode *endless)
{
    if (endless == NULL || !endless->enabled || endless->incompatible)
        return;
    ++endless->current_loop;
    endless->died = false;
    endless->ending = false;
}

void EndlessMode_OnGameplayFrame(EndlessMode *endless, const GameplayState *game)
{
    u8 hits;
    int lane;

    if (endless == NULL || game == NULL || !endless->enabled ||
        endless->incompatible || endless->ending || endless->died)
        return;

    hits = game->events.player_hit_mask;
    for (lane = 0; lane < 4; ++lane) {
        if (hits & (1u << lane)) {
            ++endless->total_notes_played;
            ++endless->total_notes_hit;
            ++endless->tally_combo;
            if (endless->tally_combo > endless->tally_max_combo)
                endless->tally_max_combo = endless->tally_combo;
        }
    }

    if (game->events.player_missed || game->events.mine_hit) {
        ++endless->total_notes_played;
        endless->tally_combo = 0;
    }
}

void EndlessMode_PrepareLoop(EndlessMode *endless, const GameplayState *game)
{
    if (endless == NULL || game == NULL || !endless->enabled)
        return;
    endless->carry_health = game->rhythm.health;
    endless->carry_score = game->rhythm.score;
    endless->carry_misses = game->misses;
}

void EndlessMode_RestoreLoop(EndlessMode *endless, GameplayState *game)
{
    if (endless == NULL || game == NULL || !endless->enabled)
        return;

    if (endless->carry_health > 0)
        game->rhythm.health = endless->carry_health;
    game->rhythm.score = endless->carry_score;
    game->misses = endless->carry_misses;
    game->rhythm.combo = (u16)(endless->tally_combo > 0xFFFFu
        ? 0xFFFFu : endless->tally_combo);
    EndlessMode_OnSongStart(endless);
}

void EndlessMode_OnDeath(EndlessMode *endless)
{
    if (endless == NULL || !endless->enabled)
        return;
    endless->died = true;
    endless->ending = true;
}
