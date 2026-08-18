#ifndef FNF_PS2_SONG_EVENTS_H
#define FNF_PS2_SONG_EVENTS_H

#include "fixed.h"
#include <stddef.h>

typedef enum SongEventKind {
    SONG_EVENT_GENERIC = 0,
    SONG_EVENT_FOCUS_CAMERA = 1
} SongEventKind;

typedef struct SongEventRecord {
    s32 time_us;
    u16 kind;
    u16 flags;
    float arg0;
    float arg1;
    u32 name_offset;
    u32 value_offset;
} __attribute__((packed)) SongEventRecord;

typedef struct SongEventStream {
    void *blob;
    size_t blob_size;
    SongEventRecord *records;
    char *strings;
    u32 string_bytes;
    u32 count;
    u32 next_index;
    boolean loaded;
} SongEventStream;

typedef void (*SongEventDispatch)(
    void *user,
    const SongEventRecord *event,
    const char *name,
    const char *value_json);

boolean SongEvents_Load(SongEventStream *events, const char *path);
void SongEvents_Free(SongEventStream *events);
void SongEvents_Reset(SongEventStream *events);
void SongEvents_Tick(
    SongEventStream *events,
    fixed_t song_time,
    SongEventDispatch dispatch,
    void *user);

#endif
