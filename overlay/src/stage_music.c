#include "stage_music.h"
#include "audio.h"

typedef struct
{
    StageId id;
    const char *path;
    u32 sectors;
    u8 channel;
    fixed_t speed[2];
} StageMusicDef;

#include "remix_audio_generated.h"

static const StageMusicDef *StageMusic_Find(StageId id, StageDiff difficulty)
{
    unsigned int i;
    if (difficulty != StageDiff_Erect && difficulty != StageDiff_Nightmare)
        return NULL;
    for (i = 0; i < sizeof(stage_music_defs) / sizeof(stage_music_defs[0]); i++)
        if (stage_music_defs[i].id == id)
            return &stage_music_defs[i];
    return NULL;
}

fixed_t StageMusic_Speed(StageId id, StageDiff difficulty, fixed_t fallback)
{
    const StageMusicDef *music = StageMusic_Find(id, difficulty);
    return music ? music->speed[difficulty - StageDiff_Erect] : fallback;
}

void StageMusic_Load(Stage *state)
{
    const StageMusicDef *music = StageMusic_Find(state->stage_id, state->stage_diff);
    state->music_channel = state->stage_def->music_channel;
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
