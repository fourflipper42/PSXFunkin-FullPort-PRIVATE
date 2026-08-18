#ifndef FNF_PS2_ASSET_FILE_H
#define FNF_PS2_ASSET_FILE_H

#include "disc.h"
#include <stdio.h>

typedef enum AssetFileBackend {
    ASSET_FILE_NONE = 0,
    ASSET_FILE_HOST,
    ASSET_FILE_DISC
} AssetFileBackend;

typedef struct AssetFile {
    AssetFileBackend backend;
    FILE *host;
    DiscFile disc;
    u32 size;
} AssetFile;

boolean AssetFile_Open(AssetFile *file, const char *path);
void AssetFile_Close(AssetFile *file);
size_t AssetFile_Read(AssetFile *file, void *dst, size_t bytes);
boolean AssetFile_Seek(AssetFile *file, u32 offset);
u32 AssetFile_Tell(const AssetFile *file);
u32 AssetFile_Size(const AssetFile *file);
boolean AssetFile_IsOpen(const AssetFile *file);

#endif
