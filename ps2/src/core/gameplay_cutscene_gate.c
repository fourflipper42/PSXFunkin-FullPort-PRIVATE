#include "gameplay.h"

#include "cutscene_controller.h"

void Gameplay_TickCore(GameplayState *state, const Pad *pad);

void Gameplay_Tick(GameplayState *state, const Pad *pad)
{
    if (CutsceneController_Active())
        return;
    Gameplay_TickCore(state, pad);
}
