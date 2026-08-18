#ifndef FNF_PS2_STORY_SESSION_H
#define FNF_PS2_STORY_SESSION_H

#include "song_catalog.h"
#include "story_catalog.h"

typedef enum StoryDifficulty {
    STORY_DIFFICULTY_EASY = 0,
    STORY_DIFFICULTY_NORMAL,
    STORY_DIFFICULTY_HARD,
    STORY_DIFFICULTY_ERECT,
    STORY_DIFFICULTY_NIGHTMARE,
    STORY_DIFFICULTY_COUNT
} StoryDifficulty;

typedef struct StorySession {
    const StoryCatalog *story;
    const SongCatalog *songs;
    u16 level_index;
    u16 song_index;
    StoryDifficulty difficulty;
    boolean active;
} StorySession;

const char *StoryDifficulty_Name(StoryDifficulty difficulty);
boolean StorySession_LevelSupportsDifficulty(
    const StoryCatalog *story,
    const SongCatalog *songs,
    u16 level_index,
    StoryDifficulty difficulty);
boolean StorySession_Start(
    StorySession *session,
    const StoryCatalog *story,
    const SongCatalog *songs,
    u16 level_index,
    StoryDifficulty difficulty);
void StorySession_Stop(StorySession *session);
boolean StorySession_CurrentSong(
    const StorySession *session,
    SongCatalogEntry *entry);
boolean StorySession_Advance(StorySession *session);

#endif
