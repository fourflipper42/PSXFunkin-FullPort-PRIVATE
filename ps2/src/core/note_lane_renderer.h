#ifndef FNF_PS2_NOTE_LANE_RENDERER_H
#define FNF_PS2_NOTE_LANE_RENDERER_H

#include "gameplay.h"
#include "note_style.h"

void NoteLaneRenderer_Reset(void);
void NoteLaneRenderer_SetLayout(boolean hide_opponent, boolean center_player);
void NoteLaneRenderer_Tick(GameplayState *game, const Pad *pad);
void NoteLaneRenderer_Draw(
    GSGLOBAL *gs,
    const NoteStyle *style,
    const GameplayState *game,
    const Pad *pad);

#endif
