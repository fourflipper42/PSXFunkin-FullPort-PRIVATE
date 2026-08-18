#include "song_events.h"

#include "asset_file.h"
#include "mem.h"
#include <string.h>

typedef struct SongEventHeader {
    char magic[4];
    u16 version;
    u16 flags;
    u32 count;
    u32 record_size;
    u32 string_bytes;
    u32 reserved;
} __attribute__((packed)) SongEventHeader;

#define SONG_EVENT_VERSION 1

static const char *event_string(const SongEventStream *events, u32 offset)
{
    const char *value;
    size_t remaining;

    if (events == NULL || events->strings == NULL || offset >= events->string_bytes)
        return NULL;
    value = events->strings + offset;
    remaining = events->string_bytes - offset;
    if (memchr(value, '\0', remaining) == NULL)
        return NULL;
    return value;
}

boolean SongEvents_Load(SongEventStream *events, const char *path)
{
    AssetFile file;
    SongEventHeader *header;
    size_t records_bytes;
    size_t minimum;
    size_t got;
    u32 i;

    if (events == NULL || path == NULL)
        return false;

    memset(events, 0, sizeof(*events));
    memset(&file, 0, sizeof(file));
    if (!AssetFile_Open(&file, path))
        return false;

    events->blob_size = AssetFile_Size(&file);
    if (events->blob_size < sizeof(SongEventHeader))
        goto fail;

    events->blob = Mem_Alloc(events->blob_size);
    if (events->blob == NULL)
        goto fail;
    got = AssetFile_Read(&file, events->blob, events->blob_size);
    AssetFile_Close(&file);
    if (got != events->blob_size)
        goto fail;

    header = (SongEventHeader *)events->blob;
    if (memcmp(header->magic, "FEVT", 4) != 0 ||
        header->version != SONG_EVENT_VERSION ||
        header->record_size != sizeof(SongEventRecord))
        goto fail;

    records_bytes = (size_t)header->count * sizeof(SongEventRecord);
    if (header->count != 0 && records_bytes / sizeof(SongEventRecord) != header->count)
        goto fail;
    minimum = sizeof(SongEventHeader) + records_bytes + (size_t)header->string_bytes;
    if (minimum > events->blob_size)
        goto fail;

    events->records = (SongEventRecord *)((u8 *)events->blob + sizeof(SongEventHeader));
    events->strings = (char *)events->records + records_bytes;
    events->string_bytes = header->string_bytes;
    events->count = header->count;

    for (i = 0; i < events->count; ++i) {
        if (event_string(events, events->records[i].name_offset) == NULL ||
            event_string(events, events->records[i].value_offset) == NULL)
            goto fail;
        if (i > 0 && events->records[i].time_us < events->records[i - 1].time_us)
            goto fail;
    }

    events->loaded = true;
    return true;

fail:
    AssetFile_Close(&file);
    SongEvents_Free(events);
    return false;
}

void SongEvents_Free(SongEventStream *events)
{
    if (events == NULL)
        return;
    if (events->blob != NULL)
        Mem_Free(events->blob);
    memset(events, 0, sizeof(*events));
}

void SongEvents_Reset(SongEventStream *events)
{
    if (events != NULL)
        events->next_index = 0;
}

void SongEvents_Tick(
    SongEventStream *events,
    fixed_t song_time,
    SongEventDispatch dispatch,
    void *user)
{
    s64 song_us;

    if (events == NULL || !events->loaded || dispatch == NULL)
        return;

    song_us = ((s64)song_time * 1000000LL) / FIXED_UNIT;
    while (events->next_index < events->count) {
        const SongEventRecord *event = &events->records[events->next_index];
        const char *name;
        const char *value;

        if ((s64)event->time_us > song_us)
            break;

        name = event_string(events, event->name_offset);
        value = event_string(events, event->value_offset);
        if (name != NULL && value != NULL)
            dispatch(user, event, name, value);
        ++events->next_index;
    }
}
