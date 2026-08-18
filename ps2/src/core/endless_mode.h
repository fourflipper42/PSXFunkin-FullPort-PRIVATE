#ifndef FNF_PS2_ENDLESS_MODE_H
#define FNF_PS2_ENDLESS_MODE_H

#include "gameplay.h"

typedef struct EndlessMode {
    boolean enabled;
    boolean incompatible;
    boolean ending;
    boolean died;
    u32 current_loop;
    u32 total_notes_hit;
    u32 total_notes_played;
    u32 tally_combo;
    u32 tally_max_combo;
    s16 carry_health;
    s32 carry_score;
    u32 carry_misses;
} EndlessMode;

void EndlessMode_Init(EndlessMode *endless, boolean enabled);
boolean EndlessMode_SongCompatible(const char *song_id, const char *variation);
void EndlessMode_SetSong(
    EndlessMode *endless,
    const char *song_id,
    const char *variation,
    boolean story_mode);
void EndlessMode_Toggle(EndlessMode *endless);
void EndlessMode_OnSongStart(EndlessMode *endless);
void EndlessMode_OnGameplayFrame(EndlessMode *endless, const GameplayState *game);
void EndlessMode_PrepareLoop(EndlessMode *endless, const GameplayState *game);
void EndlessMode_RestoreLoop(EndlessMode *endless, GameplayState *game);
void EndlessMode_OnDeath(EndlessMode *endless);

#endif
