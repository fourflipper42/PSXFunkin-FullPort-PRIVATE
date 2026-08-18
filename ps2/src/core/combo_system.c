#include "combo_system.h"

#include <string.h>

void ComboSystem_Init(ComboSystem *combo)
{
    if (combo == NULL)
        return;
    memset(combo, 0, sizeof(*combo));
    combo->popups_enabled = true;
    combo->swoosh_enabled = true;
    combo->sound_enabled = true;
    combo->swoosh_threshold = 1;
    combo->position = COMBO_SWOOSH_DEFAULT;
    combo->swoosh_due_step = -1;
}

void ComboSystem_Configure(
    ComboSystem *combo,
    boolean popups,
    boolean swoosh,
    boolean sound,
    boolean reverse_numbers,
    u16 threshold,
    ComboSwooshPosition position)
{
    if (combo == NULL)
        return;
    combo->popups_enabled = popups;
    combo->swoosh_enabled = swoosh;
    combo->sound_enabled = sound;
    combo->reverse_numbers = reverse_numbers;
    combo->swoosh_threshold = threshold == 0 ? 1 : threshold;
    if (position < COMBO_SWOOSH_LEFT || position > COMBO_SWOOSH_RIGHT)
        position = COMBO_SWOOSH_DEFAULT;
    combo->position = position;
}

void ComboSystem_ResetSong(ComboSystem *combo)
{
    boolean popups;
    boolean swoosh;
    boolean sound;
    boolean reverse;
    u16 threshold;
    ComboSwooshPosition position;

    if (combo == NULL)
        return;
    popups = combo->popups_enabled;
    swoosh = combo->swoosh_enabled;
    sound = combo->sound_enabled;
    reverse = combo->reverse_numbers;
    threshold = combo->swoosh_threshold;
    position = combo->position;
    memset(combo, 0, sizeof(*combo));
    ComboSystem_Configure(combo, popups, swoosh, sound, reverse, threshold, position);
    combo->swoosh_due_step = -1;
}

void ComboSystem_OnGameplayFrame(ComboSystem *combo, const GameplayState *game)
{
    u8 hits;
    u32 hit_count = 0;
    int lane;

    if (combo == NULL || game == NULL || !game->loaded ||
        game->paused || game->dead || game->finished)
        return;

    hits = game->events.player_hit_mask;
    for (lane = 0; lane < 4; ++lane) {
        if (hits & (1u << lane))
            ++hit_count;
    }

    if (game->events.player_missed || game->events.mine_hit || game->rhythm.combo == 0) {
        combo->grouped_combo = 0;
        combo->swoosh_due_step = -1;
    }

    if (hit_count != 0) {
        if (combo->popups_enabled && game->rhythm.combo >= 9) {
            combo->popup_pending = true;
            combo->popup_combo = game->rhythm.combo;
        }

        if (combo->swoosh_enabled) {
            /* The supplied script groups note hits and schedules the swoosh a
             * short conductor-step distance after the last hit. It used
             * BPM/16 directly as a step offset, so preserve that quirk. */
            combo->grouped_combo += hit_count;
            combo->swoosh_due_step = game->song_step +
                (s32)(game->rhythm.last_bpm / 16u);
            if (combo->swoosh_due_step <= game->song_step)
                combo->swoosh_due_step = game->song_step + 1;
        }
    }

    if (combo->swoosh_enabled && combo->swoosh_due_step >= 0 &&
        game->song_step >= combo->swoosh_due_step &&
        combo->grouped_combo >= combo->swoosh_threshold &&
        game->rhythm.combo != 0) {
        combo->swoosh_pending = true;
        combo->swoosh_combo = combo->grouped_combo;
        combo->grouped_combo = 0;
        combo->swoosh_due_step = -1;
    }
}

boolean ComboSystem_TakePopup(ComboSystem *combo, u32 *value)
{
    if (combo == NULL || !combo->popup_pending)
        return false;
    if (value != NULL)
        *value = combo->popup_combo;
    combo->popup_pending = false;
    return true;
}

boolean ComboSystem_TakeSwoosh(ComboSystem *combo, u32 *value, boolean *play_sound)
{
    if (combo == NULL || !combo->swoosh_pending)
        return false;
    if (value != NULL)
        *value = combo->swoosh_combo;
    if (play_sound != NULL)
        *play_sound = combo->sound_enabled;
    combo->swoosh_pending = false;
    return true;
}
