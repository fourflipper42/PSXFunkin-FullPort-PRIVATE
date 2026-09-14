#include "stage_music.h"
#include "audio.h"

typedef struct
{
    StageId id;
    const char *path;
    u32 sectors;
    u8 channel;
    StageDiff first, last;
    fixed_t speed[3];
} StageMusicDef;

#include "remix_audio_generated.h"
#include "base_audio_generated.h"

static const StageMusicDef *StageMusic_Find(StageId id, StageDiff difficulty)
{
    unsigned int i;
    for (i = 0; i < sizeof(stage_music_defs) / sizeof(stage_music_defs[0]); i++)
        if (stage_music_defs[i].id == id && difficulty >= stage_music_defs[i].first && difficulty <= stage_music_defs[i].last)
            return &stage_music_defs[i];
    for (i = 0; i < sizeof(base_music_defs) / sizeof(base_music_defs[0]); i++)
        if (base_music_defs[i].id == id && difficulty >= base_music_defs[i].first && difficulty <= base_music_defs[i].last)
            return &base_music_defs[i];
    return NULL;
}

fixed_t StageMusic_Speed(StageId id, StageDiff difficulty, fixed_t fallback)
{
    const StageMusicDef *music = StageMusic_Find(id, difficulty);
    return music ? music->speed[difficulty - music->first] : fallback;
}

void StageMusic_Load(Stage *state)
{
    const StageMusicDef *music = StageMusic_Find(state->stage_id, state->stage_diff);
    state->music_channel = state->stage_def->music_channel;
    state->music_separate_vocals = (music != NULL);
    /* Playback starts on the full mix, including before the first successful
       player note. A first-note miss must be able to switch to the muted mix. */
    state->flag |= STAGE_FLAG_VOCAL_ACTIVE;
    if (music)
    {
        IO_FindFile(&state->music_file, music->path);
        /* Audio_PlayXA_File divides by logical sector size, even for raw XA. */
        state->music_file.size = music->sectors * IO_SECT_SIZE;
        state->music_channel = music->channel;
    }
    else
        Audio_GetXAFile(&state->music_file, state->stage_def->music_track);
    IO_SeekFile(&state->music_file);
}
