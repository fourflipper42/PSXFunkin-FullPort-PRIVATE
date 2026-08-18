#ifndef FNF_PS2_SSERAFIM_RUNTIME_H
#define FNF_PS2_SSERAFIM_RUNTIME_H

#include "character.h"
#include "gameplay.h"
#include "stage.h"

boolean SserafimRuntime_Begin(GSGLOBAL *gs, Stage *stage, const char *base_path);
void SserafimRuntime_End(void);
boolean SserafimRuntime_Active(void);
void SserafimRuntime_Tick(fixed_t elapsed);
void SserafimRuntime_Beat(s32 beat);
void SserafimRuntime_DrawRange(
    GSGLOBAL *gs,
    const StageCamera *camera,
    s32 z_min,
    s32 z_max);
boolean SserafimRuntime_HandleEvent(const char *name, const char *value);
void SserafimRuntime_PlayHitAnimations(
    const GameplayState *game,
    Character *player,
    Character *opponent,
    Character *girlfriend);
void SserafimRuntime_DrawOverlay(GSGLOBAL *gs);

#endif
