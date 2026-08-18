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
    u64 base_frame;
} SongStream;

boolean SongStream_Open(SongStream *stream, const char *inst_path, const char *voices_path);
void SongStream_Close(SongStream *stream);
void SongStream_Tick(SongStream *stream);
void SongStream_SetVoices(SongStream *stream, boolean enabled);
boolean SongStream_SeekFrame(SongStream *stream, u64 frame);
u64 SongStream_PlayedFrames(const SongStream *stream);
fixed_t SongStream_PlayedSeconds(const SongStream *stream);
boolean SongStream_Finished(const SongStream *stream);

#endif
