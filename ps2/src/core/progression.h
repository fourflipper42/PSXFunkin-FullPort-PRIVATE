#ifndef FNF_PS2_PROGRESSION_H
#define FNF_PS2_PROGRESSION_H

#include "story_catalog.h"

#define PROGRESSION_MAX_STORY_LEVELS 64

typedef struct ProgressionState {
    u64 completed_story_levels;
} ProgressionState;

void Progression_Reset(ProgressionState *state);
boolean Progression_IsLevelComplete(const ProgressionState *state, u16 level_index);
boolean Progression_IsLevelUnlocked(
    const ProgressionState *state,
    const StoryCatalog *story,
    u16 level_index);
boolean Progression_CompleteLevel(
    ProgressionState *state,
    const StoryCatalog *story,
    u16 level_index);
boolean Progression_PicoUnlocked(
    const ProgressionState *state,
    const StoryCatalog *story);

#endif
