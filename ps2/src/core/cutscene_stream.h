#ifndef FNF_PS2_CUTSCENE_STREAM_H
#define FNF_PS2_CUTSCENE_STREAM_H

#include "song_stream.h"
#include "texture_asset.h"
#include <gsToolkit.h>

typedef struct CutsceneStream {
    SongStream audio;
    TextureAsset page;
    char base_path[256];
    u16 width;
    u16 height;
    u16 fps_num;
    u16 fps_den;
    u16 columns;
    u16 rows;
    u16 page_count;
    u32 frame_count;
    u32 frame_index;
    u16 loaded_page;
    boolean page_loaded;
    boolean loaded;
    boolean finished;
} CutsceneStream;

boolean CutsceneStream_Open(
    GSGLOBAL *gs,
    CutsceneStream *stream,
    const char *base_path);
void CutsceneStream_Close(CutsceneStream *stream);
void CutsceneStream_Tick(GSGLOBAL *gs, CutsceneStream *stream);
boolean CutsceneStream_SetPaused(CutsceneStream *stream, boolean paused);
boolean CutsceneStream_Finished(const CutsceneStream *stream);
void CutsceneStream_Draw(
    GSGLOBAL *gs,
    const CutsceneStream *stream,
    int z,
    u64 color);

#endif
