#include "song_stream.h"

#include <string.h>

#define SONG_OUTPUT_CHUNK_BYTES 8192
#define SONG_OUTPUT_FRAMES (SONG_OUTPUT_CHUNK_BYTES / AUDIO_FRAME_BYTES)
#define SONG_SOURCE_MAX_RATE 3
#define SONG_SOURCE_FRAMES (SONG_OUTPUT_FRAMES * SONG_SOURCE_MAX_RATE + 4)
#define SONG_SOURCE_SAMPLES (SONG_SOURCE_FRAMES * 2)
#define SONG_OUTPUT_SAMPLES (SONG_OUTPUT_FRAMES * 2)

static s16 inst_buffer[SONG_SOURCE_SAMPLES] __attribute__((aligned(64)));
static s16 voice_buffer[SONG_SOURCE_SAMPLES] __attribute__((aligned(64)));
static s16 mix_buffer[SONG_OUTPUT_SAMPLES] __attribute__((aligned(64)));

static s16 mix_sample(s16 inst, s16 voice)
{
    s32 mixed = (s32)inst + (s32)voice;
    if (mixed > 32767)
        mixed = 32767;
    else if (mixed < -32768)
        mixed = -32768;
    return (s16)mixed;
}

static s16 lerp_sample(s16 a, s16 b, u32 frac)
{
    s32 delta = (s32)b - (s32)a;
    return (s16)((s32)a + ((delta * (s32)frac) >> FIXED_SHIFT));
}

static u32 source_remaining(const SongStream *stream)
{
    if (stream == NULL || stream->source_buffer_cursor >= stream->source_buffer_frames)
        return 0;
    return stream->source_buffer_frames - stream->source_buffer_cursor;
}

static void compact_source(SongStream *stream)
{
    u32 remaining;
    size_t samples;

    if (stream == NULL || stream->source_buffer_cursor == 0)
        return;
    remaining = source_remaining(stream);
    samples = (size_t)remaining * 2u;
    if (remaining != 0) {
        memmove(inst_buffer,
            inst_buffer + ((size_t)stream->source_buffer_cursor * 2u),
            samples * sizeof(s16));
        memmove(voice_buffer,
            voice_buffer + ((size_t)stream->source_buffer_cursor * 2u),
            samples * sizeof(s16));
    }
    stream->source_buffer_frames = remaining;
    stream->source_buffer_cursor = 0;
}

static void fill_source(SongStream *stream, u32 needed_frames)
{
    if (stream == NULL || stream->source_eof)
        return;

    if (source_remaining(stream) >= needed_frames)
        return;
    compact_source(stream);

    while (stream->source_buffer_frames < needed_frames && !stream->source_eof) {
        u32 room_frames = SONG_SOURCE_FRAMES - stream->source_buffer_frames;
        size_t request;
        size_t inst_read;
        size_t voice_read = 0;
        u32 got_frames;
        s16 *inst_dst;
        s16 *voice_dst;

        if (room_frames == 0)
            break;
        request = (size_t)room_frames * AUDIO_FRAME_BYTES;
        inst_dst = inst_buffer + ((size_t)stream->source_buffer_frames * 2u);
        voice_dst = voice_buffer + ((size_t)stream->source_buffer_frames * 2u);

        inst_read = AssetFile_Read(&stream->inst, inst_dst, request);
        inst_read &= ~(size_t)(AUDIO_FRAME_BYTES - 1);
        got_frames = (u32)(inst_read / AUDIO_FRAME_BYTES);
        if (got_frames == 0) {
            stream->source_eof = true;
            break;
        }

        memset(voice_dst, 0, inst_read);
        if (stream->has_voices) {
            voice_read = AssetFile_Read(&stream->voices, voice_dst, inst_read);
            voice_read &= ~(size_t)(AUDIO_FRAME_BYTES - 1);
            if (voice_read < inst_read)
                memset((u8 *)voice_dst + voice_read, 0, inst_read - voice_read);
        }

        stream->source_buffer_frames += got_frames;
        if (inst_read < request)
            stream->source_eof = true;
    }
}

boolean SongStream_Open(SongStream *stream, const char *inst_path, const char *voices_path)
{
    if (stream == NULL || inst_path == NULL || !Audio_Ready())
        return false;

    memset(stream, 0, sizeof(*stream));
    if (!AssetFile_Open(&stream->inst, inst_path))
        return false;

    if (voices_path != NULL && AssetFile_Open(&stream->voices, voices_path))
        stream->has_voices = true;

    Audio_Stop();
    stream->voices_enabled = true;
    stream->active = true;
    stream->finished = false;
    stream->paused = false;
    stream->source_eof = false;
    stream->base_frame = 0;
    stream->paused_frame = 0;
    stream->playback_rate = FIXED_DEC(1, 1);
    stream->source_phase = 0;
    stream->source_buffer_frames = 0;
    stream->source_buffer_cursor = 0;
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
    u32 output_frames;
    u32 needed_source;
    u32 remaining;
    u32 produced = 0;
    u32 i;
    u64 advance;
    u32 consumed;

    if (stream == NULL || !stream->active || stream->finished || stream->paused)
        return;

    available = Audio_AvailableBytes();
    if (available < AUDIO_FRAME_BYTES)
        return;

    output_frames = (u32)((size_t)available / AUDIO_FRAME_BYTES);
    if (output_frames > SONG_OUTPUT_FRAMES)
        output_frames = SONG_OUTPUT_FRAMES;
    if (output_frames == 0)
        return;

    needed_source = (u32)(((u64)stream->source_phase +
        ((u64)(output_frames - 1u) * (u64)stream->playback_rate)) >> FIXED_SHIFT) + 2u;
    if (needed_source > SONG_SOURCE_FRAMES)
        needed_source = SONG_SOURCE_FRAMES;
    fill_source(stream, needed_source);
    remaining = source_remaining(stream);
    if (remaining == 0) {
        if (stream->source_eof)
            stream->finished = true;
        return;
    }

    for (i = 0; i < output_frames; ++i) {
        u64 source_pos = (u64)stream->source_phase +
            ((u64)i * (u64)stream->playback_rate);
        u32 relative = (u32)(source_pos >> FIXED_SHIFT);
        u32 frac = (u32)(source_pos & FIXED_LAND);
        u32 frame0;
        u32 frame1;
        s16 il;
        s16 ir;
        s16 vl = 0;
        s16 vr = 0;

        if (relative >= remaining)
            break;
        frame0 = stream->source_buffer_cursor + relative;
        frame1 = frame0 + 1u;
        if (frame1 >= stream->source_buffer_frames)
            frame1 = frame0;

        il = lerp_sample(inst_buffer[frame0 * 2u], inst_buffer[frame1 * 2u], frac);
        ir = lerp_sample(inst_buffer[frame0 * 2u + 1u], inst_buffer[frame1 * 2u + 1u], frac);
        if (stream->voices_enabled && stream->has_voices) {
            vl = lerp_sample(voice_buffer[frame0 * 2u], voice_buffer[frame1 * 2u], frac);
            vr = lerp_sample(voice_buffer[frame0 * 2u + 1u], voice_buffer[frame1 * 2u + 1u], frac);
        }
        mix_buffer[produced * 2u] = mix_sample(il, vl);
        mix_buffer[produced * 2u + 1u] = mix_sample(ir, vr);
        ++produced;
    }

    if (produced == 0) {
        if (stream->source_eof)
            stream->finished = true;
        return;
    }

    Audio_QueuePCM(mix_buffer, (size_t)produced * AUDIO_FRAME_BYTES);

    advance = (u64)stream->source_phase +
        ((u64)produced * (u64)stream->playback_rate);
    consumed = (u32)(advance >> FIXED_SHIFT);
    stream->source_phase = (u32)(advance & FIXED_LAND);
    if (consumed > remaining)
        consumed = remaining;
    stream->source_buffer_cursor += consumed;

    if (stream->source_eof && source_remaining(stream) == 0)
        stream->finished = true;
}

void SongStream_SetVoices(SongStream *stream, boolean enabled)
{
    if (stream != NULL)
        stream->voices_enabled = enabled;
}

boolean SongStream_SetPlaybackRate(SongStream *stream, fixed_t rate)
{
    u64 frame;
    boolean was_paused;

    if (stream == NULL || !AssetFile_IsOpen(&stream->inst))
        return false;
    if (rate < FIXED_DEC(1, 2))
        rate = FIXED_DEC(1, 2);
    if (rate > FIXED_DEC(3, 1))
        rate = FIXED_DEC(3, 1);
    if (stream->playback_rate == rate)
        return true;

    frame = SongStream_PlayedFrames(stream);
    was_paused = stream->paused;
    stream->playback_rate = rate;
    if (!SongStream_SeekFrame(stream, frame))
        return false;
    if (was_paused)
        return SongStream_Pause(stream);
    return true;
}

fixed_t SongStream_PlaybackRate(const SongStream *stream)
{
    if (stream == NULL || stream->playback_rate <= 0)
        return FIXED_DEC(1, 1);
    return stream->playback_rate;
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
    stream->paused_frame = frame;
    stream->source_phase = 0;
    stream->source_buffer_frames = 0;
    stream->source_buffer_cursor = 0;
    stream->source_eof = false;
    stream->finished = false;
    stream->paused = false;
    stream->active = true;
    return true;
}

boolean SongStream_Pause(SongStream *stream)
{
    u64 frame;

    if (stream == NULL || stream->paused || !AssetFile_IsOpen(&stream->inst))
        return false;

    frame = SongStream_PlayedFrames(stream);
    Audio_Stop();
    stream->paused_frame = frame;
    stream->base_frame = frame;
    stream->source_phase = 0;
    stream->source_buffer_frames = 0;
    stream->source_buffer_cursor = 0;
    stream->source_eof = false;
    stream->active = false;
    stream->paused = true;
    return true;
}

boolean SongStream_Resume(SongStream *stream)
{
    u64 frame;

    if (stream == NULL || !stream->paused || !AssetFile_IsOpen(&stream->inst))
        return false;

    frame = stream->paused_frame;
    if (!SongStream_SeekFrame(stream, frame)) {
        stream->paused = true;
        stream->active = false;
        return false;
    }
    return true;
}

u64 SongStream_PlayedFrames(const SongStream *stream)
{
    u64 played;
    if (stream == NULL)
        return 0;
    if (stream->paused)
        return stream->paused_frame;
    played = Audio_PlayedFrames();
    return stream->base_frame +
        ((played * (u64)SongStream_PlaybackRate(stream)) >> FIXED_SHIFT);
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
    if (stream->paused)
        return false;
    return stream->finished && Audio_QueuedBytes() == 0;
}

boolean SongStream_Paused(const SongStream *stream)
{
    return stream != NULL && stream->paused;
}
