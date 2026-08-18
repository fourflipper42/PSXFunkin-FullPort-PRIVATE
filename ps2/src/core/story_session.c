#include "story_session.h"

#include <string.h>

static boolean resolve_story_song(
    const SongCatalog *songs,
    const char *song_id,
    StoryDifficulty difficulty,
    SongCatalogEntry *entry)
{
    const char *difficulty_name = StoryDifficulty_Name(difficulty);
    const char *variation = "default";

    if (songs == NULL || song_id == NULL || difficulty_name == NULL || entry == NULL)
        return false;

    if (difficulty == STORY_DIFFICULTY_ERECT ||
        difficulty == STORY_DIFFICULTY_NIGHTMARE) {
        variation = "erect";
        if (SongCatalog_Find(songs, song_id, variation, difficulty_name, entry))
            return true;
        /* A softcoded song may expose the difficulty without a dedicated
         * erect variation. Preserve that possibility instead of rejecting it. */
        return SongCatalog_Find(songs, song_id, "default", difficulty_name, entry);
    }

    return SongCatalog_Find(songs, song_id, variation, difficulty_name, entry);
}

const char *StoryDifficulty_Name(StoryDifficulty difficulty)
{
    switch (difficulty) {
        case STORY_DIFFICULTY_EASY: return "easy";
        case STORY_DIFFICULTY_NORMAL: return "normal";
        case STORY_DIFFICULTY_HARD: return "hard";
        case STORY_DIFFICULTY_ERECT: return "erect";
        case STORY_DIFFICULTY_NIGHTMARE: return "nightmare";
        default: return NULL;
    }
}

boolean StorySession_LevelSupportsDifficulty(
    const StoryCatalog *story,
    const SongCatalog *songs,
    u16 level_index,
    StoryDifficulty difficulty)
{
    StoryLevelEntry level;
    u16 i;

    if (!StoryCatalog_GetLevel(story, level_index, &level) ||
        !(level.flags & STORY_LEVEL_VISIBLE))
        return false;

    for (i = 0; i < level.song_count; ++i) {
        const char *song_id = StoryCatalog_GetSong(story, level_index, i);
        SongCatalogEntry entry;
        if (!resolve_story_song(songs, song_id, difficulty, &entry))
            return false;
    }
    return level.song_count != 0;
}

boolean StorySession_Start(
    StorySession *session,
    const StoryCatalog *story,
    const SongCatalog *songs,
    u16 level_index,
    StoryDifficulty difficulty)
{
    if (session == NULL || story == NULL || songs == NULL ||
        !StorySession_LevelSupportsDifficulty(story, songs, level_index, difficulty))
        return false;

    memset(session, 0, sizeof(*session));
    session->story = story;
    session->songs = songs;
    session->level_index = level_index;
    session->difficulty = difficulty;
    session->active = true;
    return true;
}

void StorySession_Stop(StorySession *session)
{
    if (session != NULL)
        memset(session, 0, sizeof(*session));
}

boolean StorySession_CurrentSong(
    const StorySession *session,
    SongCatalogEntry *entry)
{
    const char *song_id;

    if (session == NULL || !session->active || entry == NULL)
        return false;
    song_id = StoryCatalog_GetSong(
        session->story,
        session->level_index,
        session->song_index);
    if (song_id == NULL)
        return false;
    return resolve_story_song(
        session->songs,
        song_id,
        session->difficulty,
        entry);
}

boolean StorySession_Advance(StorySession *session)
{
    StoryLevelEntry level;

    if (session == NULL || !session->active ||
        !StoryCatalog_GetLevel(session->story, session->level_index, &level))
        return false;

    ++session->song_index;
    if (session->song_index >= level.song_count) {
        session->active = false;
        return false;
    }
    return true;
}
