#include "stage.h"

#include "presentation_registry.h"
#include "weekend1_visual.h"

boolean Stage_LoadCore(GSGLOBAL *gs, Stage *stage, const char *base_path);
void Stage_ForgetCore(Stage *stage);
void Stage_DrawRangeCore(
    GSGLOBAL *gs,
    const Stage *stage,
    const StageCamera *camera,
    s32 z_min,
    s32 z_max);

boolean Stage_Load(GSGLOBAL *gs, Stage *stage, const char *base_path)
{
    boolean result = Stage_LoadCore(gs, stage, base_path);
    if (result)
        PresentationRegistry_RegisterStage(stage);
    else
        PresentationRegistry_Reset();
    return result;
}

void Stage_Forget(Stage *stage)
{
    PresentationRegistry_UnregisterStage(stage);
    Stage_ForgetCore(stage);
}

void Stage_DrawRange(
    GSGLOBAL *gs,
    const Stage *stage,
    const StageCamera *camera,
    s32 z_min,
    s32 z_max)
{
    Stage_DrawRangeCore(gs, stage, camera, z_min, z_max);
    Weekend1Visual_DrawRange(gs, stage, camera, z_min, z_max);
}
