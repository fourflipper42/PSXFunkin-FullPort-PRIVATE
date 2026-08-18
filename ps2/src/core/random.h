#ifndef FNF_PS2_RANDOM_H
#define FNF_PS2_RANDOM_H

#include "psx.h"

void RandomSeed(u32 seed);
u32 RandomGetSeed(void);
u8 Random8(void);
u16 Random16(void);
u32 Random32(void);
s32 RandomRange(s32 x, s32 y);

#endif
