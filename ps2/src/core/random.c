#include "random.h"

static u32 rand_seed;

void RandomSeed(u32 seed)
{
    rand_seed = seed;
}

u32 RandomGetSeed(void)
{
    return rand_seed;
}

u8 Random8(void)
{
    return (u8)(Random16() >> 4);
}

u16 Random16(void)
{
    rand_seed = rand_seed * 214013L + 2531011L;
    return (u16)(rand_seed >> 16);
}

u32 Random32(void)
{
    return ((u32)Random16() << 16) | Random16();
}

s32 RandomRange(s32 x, s32 y)
{
    if (y <= x)
        return x;
    return x + (s32)(Random16() % ((u32)(y - x) + 1u));
}
