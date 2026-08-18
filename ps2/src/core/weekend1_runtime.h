#ifndef FNF_PS2_WEEKEND1_RUNTIME_H
#define FNF_PS2_WEEKEND1_RUNTIME_H

#include "gameplay.h"
#include "note_kind_runtime.h"

void Weekend1Runtime_BeginSong(
    const char *song_id,
    GameplayState *game,
    const NoteKindRuntime *note_kinds);
void Weekend1Runtime_EndSong(void);
void Weekend1Runtime_Tick(
    GameplayState *game,
    const NoteKindRuntime *note_kinds,
    fixed_t elapsed);
boolean Weekend1Runtime_CanFlash(void);
boolean Weekend1Runtime_SpecialDeath(void);

#endif
