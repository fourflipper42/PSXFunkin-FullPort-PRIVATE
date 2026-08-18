#include "song_stream.h"

#include <string.h>

#define SONG_CHUNK_BYTES 8192
#define SONG_CHUNK_SAMPLES (SONG_CHUNK_BYTES / 2)

static s16 inst_buffer[SONG_CHUNK_SAMPLES] __attribute__((aligned(64)));
static s16 voice_buffer[SONG_CHUNK_SAMPLES] __attribute__((aligned(64)));
static s16 mix_buffer[SONG_CHUNK_SAMPLES] __attribute__((aligned(64)));

static s16 mix_sample(s16 inst, s16 voice)
{
    s32 mixed = (s32)inst + (s32)voice;
    if (mixed > 32767)
        mixed = 32767;
    else if (mixed < -32768)
        mixed = -32768;
    return (s16)mixed;
}

boolean SongStream_Open(SongStream *stream, const char *inst_path, const char *voices_path)
{
    if (stream == NULL || inst_path == NULL || !Audio_Ready())
        return false;

    memset(stream, 0, sizeof(*stream));
    if (!AssetFile_Open(&stream->inst, inst_path))
        return false;

    /* Vocals are optional. Instrumental-only songs and metadata variations
     * with no resolved voice stems must still boot and play normally. */
    if (voices_path != NULL && AssetFile_Open(&stream->voices, voices_path))
        stream->has_voices = true;

    Audio_Stop();
    stream->voices_enabled = true;
    stream->active = true;
    stream->finished = false;
    stream->base_frame = 0;
    return true;
}

void SongStream_Close(SongStream *stream)
{
    if (stream == NULL)
        return;

    Audio_Stop();
    AssetFile_Close(&stream->inst);
    AssetFile_Close(&stream->voices);
    memset(stream, 0, sizeof(*stream));
}

void SongStream_Tick(SongStream *stream)
{
    int available;
    size_t request;
    size_t inst_read;
    size_t voice_read = 0;
    size_t sample_count;
    size_t i;

    if (stream == NULL || !stream->active || stream->finished)
        return;

    available = Audio_AvailableBytes();
    if (available < AUDIO_FRAME_BYTES)
        return;

    request = (size_t)available;
    if (request > SONG_CHUNK_BYTES)
        request = SONG_CHUNK_BYTES;
    request &= ~(size_t)(AUDIO_FRAME_BYTES - 1);
    if (request == 0)
        return;

    inst_read = AssetFile_Read(&stream->inst, inst_buffer, request);
    inst_read &= ~(size_t)(AUDIO_FRAME_BYTES - 1);
    if (inst_read == 0) {
        stream->finished = true;
        return;
    }

    memset(voice_buffer, 0, inst_read);
    if (stream->has_voices) {
        voice_read = AssetFile_Read(&stream->voices, voice_buffer, inst_read);
        voice_read &= ~(size_t)(AUDIO_FRAME_BYTES - 1);
        if (voice_read < inst_read)
            memset((u8 *)voice_buffer + voice_read, 0, inst_read - voice_read);
    }

    sample_count = inst_read / sizeof(s16);
    if (stream->voices_enabled && stream->has_voices) {
        for (i = 0; i < sample_count; ++i)
            mix_buffer[i] = mix_sample(inst_buffer[i], voice_buffer[i]);
    } else {
        memcpy(mix_buffer, inst_buffer, inst_read);
    }

    Audio_QueuePCM(mix_buffer, inst_read);
    if (inst_read < request)
        stream->finished = true;
}

void SongStream_SetVoices(SongStream *stream, boolean enabled)
{
    if (stream != NULL)
        stream->voices_enabled = enabled;
}

boolean SongStream_SeekFrame(SongStream *stream, u64 frame)
{
    u64 byte_offset;

    if (stream == NULL || !AssetFile_IsOpen(&stream->inst))
        return false;

    byte_offset = frame * AUDIO_FRAME_BYTES;
    if (byte_offset > 0xFFFFFFFFULL)
        return false;

    Audio_Stop();
    if (!AssetFile_Seek(&stream->inst, (u32)byte_offset))
        return false;
    if (stream->has_voices && !AssetFile_Seek(&stream->voices, (u32)byte_offset))
        return false;

    stream->base_frame = frame;
    stream->finished = false;
    stream->active = true;
    return true;
}

u64 SongStream_PlayedFrames(const SongStream *stream)
{
    if (stream == NULL)
        return 0;
    return stream->base_frame + Audio_PlayedFrames();
}

fixed_t SongStream_PlayedSeconds(const SongStream *stream)
{
    u64 frames = SongStream_PlayedFrames(stream);
    return (fixed_t)((frames << FIXED_SHIFT) / AUDIO_SAMPLE_RATE);
}

boolean SongStream_Finished(const SongStream *stream)
{
    if (stream == NULL)
        return true;
    return stream->finished && Audio_QueuedBytes() == 0;
}
