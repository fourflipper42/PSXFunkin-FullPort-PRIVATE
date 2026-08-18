#ifndef FNF_PS2_NOTE_KIND_RUNTIME_H
#define FNF_PS2_NOTE_KIND_RUNTIME_H

#include "character.h"
#include "gameplay.h"
#include "note_kinds.h"

typedef struct NoteKindHit {
    u8 kind_index;
    u8 note_type;
    u8 lane;
    boolean valid;
} NoteKindHit;

typedef struct NoteKindRuntime {
    NoteKindTable table;
    NoteKindHit player[4];
    NoteKindHit opponent[4];
    u16 last_player_pos[4];
    u16 last_opponent_pos[4];
    boolean loaded;
} NoteKindRuntime;

void NoteKindRuntime_Init(NoteKindRuntime *runtime);
boolean NoteKindRuntime_LoadForChart(
    NoteKindRuntime *runtime,
    const char *chart_path);
void NoteKindRuntime_Free(NoteKindRuntime *runtime);
void NoteKindRuntime_ResolveFrame(
    NoteKindRuntime *runtime,
    const GameplayState *game);
boolean NoteKindRuntime_PlayLaneAnimation(
    NoteKindRuntime *runtime,
    Character *character,
    const NoteKindHit *hit,
    boolean force_restart);

#endif
