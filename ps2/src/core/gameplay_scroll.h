#ifndef FNF_PS2_GAMEPLAY_SCROLL_H
#define FNF_PS2_GAMEPLAY_SCROLL_H

#include "gameplay.h"

void GameplayScroll_Reset(GameplayState *state);
boolean GameplayScroll_HandleEvent(
    GameplayState *state,
    const char *name,
    const char *value_json);
void GameplayScroll_Tick(GameplayState *state, fixed_t dt);

#endif
