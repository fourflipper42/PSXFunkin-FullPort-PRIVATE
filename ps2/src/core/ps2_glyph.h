#ifndef FNF_PS2_GLYPH_H
#define FNF_PS2_GLYPH_H

#include "fixed.h"
#include <gsKit.h>

typedef enum Ps2Glyph {
    PS2_GLYPH_CROSS = 0,
    PS2_GLYPH_CIRCLE,
    PS2_GLYPH_SQUARE,
    PS2_GLYPH_TRIANGLE,
    PS2_GLYPH_START,
    PS2_GLYPH_SELECT,
    PS2_GLYPH_L1,
    PS2_GLYPH_R1,
    PS2_GLYPH_L2,
    PS2_GLYPH_R2,
    PS2_GLYPH_DPAD_UP,
    PS2_GLYPH_DPAD_DOWN,
    PS2_GLYPH_DPAD_LEFT,
    PS2_GLYPH_DPAD_RIGHT
} Ps2Glyph;

void Ps2Glyph_SetDrawTransform(
    float x_scale,
    float y_scale,
    float x_offset,
    float y_offset);
void Ps2Glyph_Draw(
    GSGLOBAL *gs,
    Ps2Glyph glyph,
    float x,
    float y,
    float size,
    int z);
const char *Ps2Glyph_Name(Ps2Glyph glyph);

#endif
