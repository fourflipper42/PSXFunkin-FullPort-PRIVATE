#include "gameplay.h"

#include "cutscene_controller.h"

void Gameplay_TickCore(GameplayState *state, const Pad *pad);
boolean Gameplay_SetPausedCore(GameplayState *state, boolean paused);

void Gameplay_Tick(GameplayState *state, const Pad *pad)
{
    if (CutsceneController_Active())
        return;
    Gameplay_TickCore(state, pad);
}

boolean Gameplay_SetPaused(GameplayState *state, boolean paused)
{
    /* main.c owns START before the per-song input hook. Reject gameplay pause
     * changes while a Story movie is active so movie audio never drains behind
     * a frozen presentation. CROSS remains the explicit cutscene skip. */
    if (CutsceneController_Active())
        return false;
    return Gameplay_SetPausedCore(state, paused);
}
