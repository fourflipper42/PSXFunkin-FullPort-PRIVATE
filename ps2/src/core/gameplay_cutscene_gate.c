#include "gameplay.h"

#include "cutscene_controller.h"

void Gameplay_TickCore(GameplayState *state, const Pad *pad);
boolean Gameplay_SetPausedCore(GameplayState *state, boolean paused);
boolean Gameplay_IsFinishedCore(const GameplayState *state);

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

boolean Gameplay_IsFinished(const GameplayState *state)
{
    if (!Gameplay_IsFinishedCore(state))
        return false;

    /* Delay the normal results/Story advance while an ending movie is active,
     * or arm it on the first finished-state query when this song has one. */
    if (CutsceneController_Active())
        return false;
    if (CutsceneController_BeginPostSong())
        return false;
    return true;
}
