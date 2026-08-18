#ifndef FNF_PS2_HEALTH_DRAIN_H
#define FNF_PS2_HEALTH_DRAIN_H

#include "gameplay.h"

typedef enum HealthDrainLevel {
    HEALTH_DRAIN_OFF = 0,
    HEALTH_DRAIN_NOOB,
    HEALTH_DRAIN_EASY,
    HEALTH_DRAIN_NORMAL,
    HEALTH_DRAIN_HARD,
    HEALTH_DRAIN_INSANE,
    HEALTH_DRAIN_AUTO_PRO,
    HEALTH_DRAIN_ABSURD,
    HEALTH_DRAIN_LEVEL_COUNT
} HealthDrainLevel;

typedef struct HealthDrain {
    HealthDrainLevel level;
    float auto_multiplier;
    float lag_multiplier;
    boolean absurd_failed;
} HealthDrain;

void HealthDrain_Init(HealthDrain *drain, HealthDrainLevel level);
void HealthDrain_SetLevel(
    HealthDrain *drain,
    GameplayState *game,
    HealthDrainLevel level);
void HealthDrain_OnFrame(
    HealthDrain *drain,
    GameplayState *game,
    fixed_t elapsed);
const char *HealthDrain_LevelName(HealthDrainLevel level);
float HealthDrain_CurrentMultiplier(const HealthDrain *drain);

#endif
