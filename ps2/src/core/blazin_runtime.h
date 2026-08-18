#ifndef FNF_PS2_BLAZIN_RUNTIME_H
#define FNF_PS2_BLAZIN_RUNTIME_H

#include "gameplay.h"
#include "note_kind_runtime.h"

void BlazinRuntime_Begin(GameplayState *game);
void BlazinRuntime_End(void);
void BlazinRuntime_Tick(
    GameplayState *game,
    const NoteKindRuntime *note_kinds);

#endif
