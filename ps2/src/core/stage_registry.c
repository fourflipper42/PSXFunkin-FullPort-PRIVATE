#include "stage.h"

#include "darnell_intro_visual.h"
#include "presentation_registry.h"
#include "sserafim_runtime.h"
#include "timer.h"
#include "weekend1_visual.h"

boolean Stage_LoadCore(GSGLOBAL *gs, Stage *stage, const char *base_path);
void Stage_ForgetCore(Stage *stage);
void Stage_TickCore(Stage *stage);
void Stage_BeatCore(Stage *stage, s32 beat);
void Stage_DrawRangeCore(
    GSGLOBAL *gs,
    const Stage *stage,
    const StageCamera *camera,
    s32 z_min,
    s32 z_max);

boolean Stage_Load(GSGLOBAL *gs, Stage *stage, const char *base_path)
{
    boolean result = Stage_LoadCore(gs, stage, base_path);
    if (result) {
        PresentationRegistry_RegisterStage(stage);
        SserafimRuntime_Begin(gs, stage, base_path);
    } else {
        PresentationRegistry_Reset();
        SserafimRuntime_End();
    }
    return result;
}

void Stage_Forget(Stage *stage)
{
    SserafimRuntime_End();
    PresentationRegistry_UnregisterStage(stage);
    Stage_ForgetCore(stage);
}

void Stage_Tick(Stage *stage)
{
    Stage_TickCore(stage);
    SserafimRuntime_Tick(timer_presentation_dt);
}

void Stage_Beat(Stage *stage, s32 beat)
{
    /* Extra Sserafim AnimateAtlas characters own their one-shot choreography.
     * Do not force a generic beat dance here or kick1/kick2 can be interrupted. */
    Stage_BeatCore(stage, beat);
}

void Stage_DrawRange(
    GSGLOBAL *gs,
    const Stage *stage,
    const StageCamera *camera,
    s32 z_min,
    s32 z_max)
{
    Stage_DrawRangeCore(gs, stage, camera, z_min, z_max);
    SserafimRuntime_DrawRange(gs, camera, z_min, z_max);
    Weekend1Visual_DrawRange(gs, stage, camera, z_min, z_max);
    DarnellIntroVisual_DrawRange(gs, stage, camera, z_min, z_max);
}
