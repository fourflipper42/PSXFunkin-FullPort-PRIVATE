#include "note_lane_renderer.h"

#include "cutscene_controller.h"

void NoteLaneRenderer_TickCore(GameplayState *game, const Pad *pad);
void NoteLaneRenderer_DrawCore(
    GSGLOBAL *gs,
    const NoteStyle *style,
    const GameplayState *game,
    const Pad *pad);

void NoteLaneRenderer_Tick(GameplayState *game, const Pad *pad)
{
    if (CutsceneController_Active())
        return;
    NoteLaneRenderer_TickCore(game, pad);
}

void NoteLaneRenderer_Draw(
    GSGLOBAL *gs,
    const NoteStyle *style,
    const GameplayState *game,
    const Pad *pad)
{
    if (CutsceneController_Active())
        return;
    NoteLaneRenderer_DrawCore(gs, style, game, pad);
}
