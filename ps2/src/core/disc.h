#ifndef FNF_PS2_DISC_H
#define FNF_PS2_DISC_H

#include "psx.h"
#include <stddef.h>

typedef struct DiscFile {
    u32 lsn;
    u32 size;
    u32 pos;
    boolean open;
} DiscFile;

boolean Disc_Init(void);
boolean Disc_Open(DiscFile *file, const char *iso_path);
void Disc_Close(DiscFile *file);
size_t Disc_Read(DiscFile *file, void *dst, size_t bytes);
boolean Disc_Seek(DiscFile *file, u32 offset);
u32 Disc_Tell(const DiscFile *file);
u32 Disc_Size(const DiscFile *file);

#endif
