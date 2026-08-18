#ifndef FNF_PS2_SONG_STREAM_H
#define FNF_PS2_SONG_STREAM_H

#include "audio.h"
#include "asset_file.h"

typedef struct SongStream {
    AssetFile inst;
    AssetFile voices;
    boolean has_voices;
    boolean voices_enabled;
    boolean active;
    boolean finished;
    boolean paused;
    boolean source_eof;
    u64 base_frame;
    u64 paused_frame;
    fixed_t playback_rate;
    u32 source_phase;
    u32 source_buffer_frames;
    u32 source_buffer_cursor;
} SongStream;

boolean SongStream_Open(SongStream *stream, const char *inst_path, const char *voices_path);
void SongStream_Close(SongStream *stream);
void SongStream_Tick(SongStream *stream);
void SongStream_SetVoices(SongStream *stream, boolean enabled);
boolean SongStream_SetPlaybackRate(SongStream *stream, fixed_t rate);
fixed_t SongStream_PlaybackRate(const SongStream *stream);
boolean SongStream_SeekFrame(SongStream *stream, u64 frame);
boolean SongStream_Pause(SongStream *stream);
boolean SongStream_Resume(SongStream *stream);
u64 SongStream_PlayedFrames(const SongStream *stream);
fixed_t SongStream_PlayedSeconds(const SongStream *stream);
boolean SongStream_Finished(const SongStream *stream);
boolean SongStream_Paused(const SongStream *stream);

#endif
