#include "mem.h"
#include <stdlib.h>

u8 Mem_Init(void *ptr, size_t size)
{
    /* PS2SDK libc owns the EE heap. Keep this entry point for old core code. */
    (void)ptr;
    (void)size;
    return 0;
}

void *Mem_Alloc(size_t size)
{
    return malloc(size);
}

void *Mem_Alloc2(const char *sign, size_t size)
{
    (void)sign;
    return malloc(size);
}

void Mem_Free(void *ptr)
{
    free(ptr);
}
