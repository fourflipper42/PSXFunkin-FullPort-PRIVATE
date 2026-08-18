#include "stage.h"

#include "presentation_registry.h"

boolean Stage_LoadCore(GSGLOBAL *gs, Stage *stage, const char *base_path);
void Stage_ForgetCore(Stage *stage);

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
