#include "hud.h"

#include "cutscene_controller.h"
#include "sserafim_runtime.h"

void Hud_DrawCore(
    GSGLOBAL *gs,
    const HudRuntime *hud,
    const GameplayState *game,
    const FunkinSaveData *save,
    GSFONTM *font);

void Hud_Draw(
    GSGLOBAL *gs,
    const HudRuntime *hud,
    const GameplayState *game,
    const FunkinSaveData *save,
    GSFONTM *font)
{
    if (CutsceneController_Active()) {
        CutsceneController_Draw(gs);
        return;
    }
    Hud_DrawCore(gs, hud, game, save, font);
    SserafimRuntime_DrawOverlay(gs);
}
