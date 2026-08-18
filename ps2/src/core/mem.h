#ifndef FNF_PS2_MEM_H
#define FNF_PS2_MEM_H

#include "psx.h"

u8 Mem_Init(void *ptr, size_t size);
void *Mem_Alloc(size_t size);
void *Mem_Alloc2(const char *sign, size_t size);
void Mem_Free(void *ptr);

#endif
