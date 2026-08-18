#include "progression.h"

#include <string.h>

static boolean progression_level_id(
    const StoryCatalog *story,
    u16 index,
    StoryLevelEntry *entry)
{
    return StoryCatalog_GetLevel(story, index, entry) && entry->id != NULL;
}

void Progression_Reset(ProgressionState *state)
{
    if (state != NULL)
        memset(state, 0, sizeof(*state));
}

boolean Progression_IsLevelComplete(const ProgressionState *state, u16 level_index)
{
    if (state == NULL || level_index >= PROGRESSION_MAX_STORY_LEVELS)
        return false;
    return (state->completed_story_levels & ((u64)1 << level_index)) != 0;
}

boolean Progression_IsLevelUnlocked(
    const ProgressionState *state,
    const StoryCatalog *story,
    u16 level_index)
{
    StoryLevelEntry level;
    s32 previous;

    if (state == NULL || story == NULL || !story->loaded ||
        level_index >= story->level_count ||
        level_index >= PROGRESSION_MAX_STORY_LEVELS ||
        !progression_level_id(story, level_index, &level) ||
        !(level.flags & STORY_LEVEL_VISIBLE))
        return false;

    /* Tutorial is always available and does not gate Week 1. */
    if (strcmp(level.id, "tutorial") == 0)
        return true;

    /* The first visible non-tutorial level (normally Week 1) starts unlocked. */
    for (previous = (s32)level_index - 1; previous >= 0; --previous) {
        StoryLevelEntry prior;
        if (!progression_level_id(story, (u16)previous, &prior) ||
            !(prior.flags & STORY_LEVEL_VISIBLE) ||
            strcmp(prior.id, "tutorial") == 0)
            continue;
        return Progression_IsLevelComplete(state, (u16)previous);
    }

    return true;
}

boolean Progression_CompleteLevel(
    ProgressionState *state,
    const StoryCatalog *story,
    u16 level_index)
{
    StoryLevelEntry level;

    if (state == NULL || story == NULL ||
        level_index >= PROGRESSION_MAX_STORY_LEVELS ||
        !progression_level_id(story, level_index, &level))
        return false;

    state->completed_story_levels |= ((u64)1 << level_index);
    return true;
}

boolean Progression_PicoUnlocked(
    const ProgressionState *state,
    const StoryCatalog *story)
{
    u16 i;

    if (state == NULL || story == NULL || !story->loaded)
        return false;

    for (i = 0; i < story->level_count && i < PROGRESSION_MAX_STORY_LEVELS; ++i) {
        StoryLevelEntry level;
        if (!progression_level_id(story, i, &level))
            continue;
        if (strcmp(level.id, "weekend1") == 0)
            return Progression_IsLevelComplete(state, i);
    }
    return false;
}
