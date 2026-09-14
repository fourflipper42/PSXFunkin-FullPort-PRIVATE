#ifndef FRAMEBANK_H
#define FRAMEBANK_H
#include "gfx.h"
#include "framecodec.h"
typedef struct {
    IO_Data data;
    FrameCodecInfo info;
    Gfx_Tex texture;
    u16 frame;
    u16 x, y, clut_x, clut_y;
} FrameBank;
void FrameBank_Load(FrameBank *bank, const char *path, u16 x, u16 y, u16 clut_x, u16 clut_y);
void FrameBank_Free(FrameBank *bank);
void FrameBank_Invalidate(FrameBank *bank);
void FrameBank_Upload(FrameBank *bank, u16 frame);
void FrameBank_Draw(FrameBank *bank, u16 frame, s16 x, s16 y);
#endif
