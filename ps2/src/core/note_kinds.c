#include "note_kinds.h"

#include "asset_file.h"
#include "mem.h"
#include <string.h>

typedef struct NoteKindHeader {
    char magic[4];
    u16 version;
    u16 count;
    u32 record_size;
    u32 string_bytes;
} __attribute__((packed)) NoteKindHeader;

#define NOTE_KIND_VERSION 1

static const char *kind_string(const NoteKindTable *table, u32 offset)
{
    const char *value;
    size_t remaining;
    if (table == NULL || table->strings == NULL || offset >= table->string_bytes)
        return NULL;
    value = table->strings + offset;
    remaining = table->string_bytes - offset;
    return memchr(value, '\0', remaining) != NULL ? value : NULL;
}

boolean NoteKinds_Load(NoteKindTable *table, const char *path)
{
    AssetFile file;
    NoteKindHeader *header;
    size_t record_bytes;
    size_t minimum;
    size_t got;
    u16 i;

    if (table == NULL || path == NULL)
        return false;
    memset(table, 0, sizeof(*table));
    memset(&file, 0, sizeof(file));
    if (!AssetFile_Open(&file, path))
        return false;

    table->blob_size = AssetFile_Size(&file);
    if (table->blob_size < sizeof(NoteKindHeader))
        goto fail;
    table->blob = Mem_Alloc(table->blob_size);
    if (table->blob == NULL)
        goto fail;
    got = AssetFile_Read(&file, table->blob, table->blob_size);
    AssetFile_Close(&file);
    if (got != table->blob_size)
        goto fail;

    header = (NoteKindHeader *)table->blob;
    if (memcmp(header->magic, "FKND", 4) != 0 ||
        header->version != NOTE_KIND_VERSION ||
        header->record_size != sizeof(NoteKindRecord))
        goto fail;

    record_bytes = (size_t)header->count * sizeof(NoteKindRecord);
    minimum = sizeof(NoteKindHeader) + record_bytes + header->string_bytes;
    if (minimum > table->blob_size)
        goto fail;

    table->records = (NoteKindRecord *)((u8 *)table->blob + sizeof(NoteKindHeader));
    table->strings = (char *)table->records + record_bytes;
    table->string_bytes = header->string_bytes;
    table->count = header->count;
    for (i = 0; i < table->count; ++i) {
        if (kind_string(table, table->records[i].name_offset) == NULL ||
            kind_string(table, table->records[i].params_offset) == NULL)
            goto fail;
    }
    table->loaded = true;
    return true;

fail:
    AssetFile_Close(&file);
    NoteKinds_Free(table);
    return false;
}

void NoteKinds_Free(NoteKindTable *table)
{
    if (table == NULL)
        return;
    if (table->blob != NULL)
        Mem_Free(table->blob);
    memset(table, 0, sizeof(*table));
}

boolean NoteKinds_Get(const NoteKindTable *table, u8 index, NoteKindEntry *entry)
{
    const NoteKindRecord *record;
    if (table == NULL || !table->loaded || entry == NULL || index == 0 || index > table->count)
        return false;
    record = &table->records[index - 1];
    entry->name = kind_string(table, record->name_offset);
    entry->params_json = kind_string(table, record->params_offset);
    return entry->name != NULL && entry->params_json != NULL;
}

boolean NoteKinds_NameEquals(const NoteKindTable *table, u8 index, const char *name)
{
    NoteKindEntry entry;
    return name != NULL && NoteKinds_Get(table, index, &entry) && strcmp(entry.name, name) == 0;
}

static boolean json_read_string(const char **cursor, char *out, size_t out_size)
{
    const char *s = *cursor;
    size_t used = 0;
    if (*s != '"' || out == NULL || out_size == 0)
        return false;
    ++s;
    while (*s != '\0' && *s != '"') {
        unsigned char value;
        if (*s == '\\') {
            ++s;
            if (*s == '\0')
                return false;
            switch (*s) {
                case 'n': value = '\n'; break;
                case 'r': value = '\r'; break;
                case 't': value = '\t'; break;
                case '\\': value = '\\'; break;
                case '"': value = '"'; break;
                default: value = (unsigned char)*s; break;
            }
        } else {
            value = (unsigned char)*s;
        }
        if (used + 1 < out_size)
            out[used++] = (char)value;
        ++s;
    }
    if (*s != '"')
        return false;
    out[used] = '\0';
    *cursor = s + 1;
    return true;
}

boolean NoteKinds_ParamString(
    const NoteKindTable *table,
    u8 index,
    const char *param_name,
    char *out,
    size_t out_size)
{
    NoteKindEntry entry;
    const char *cursor;
    char name[64];
    char value[128];

    if (out != NULL && out_size != 0)
        out[0] = '\0';
    if (param_name == NULL || out == NULL || out_size == 0 ||
        !NoteKinds_Get(table, index, &entry))
        return false;

    cursor = entry.params_json;
    while ((cursor = strstr(cursor, "\"n\":")) != NULL) {
        cursor += 4;
        if (!json_read_string(&cursor, name, sizeof(name))) {
            ++cursor;
            continue;
        }
        if (strcmp(name, param_name) != 0)
            continue;
        cursor = strstr(cursor, "\"v\":");
        if (cursor == NULL)
            return false;
        cursor += 4;
        while (*cursor == ' ' || *cursor == '\t') ++cursor;
        if (*cursor != '"')
            return false;
        if (!json_read_string(&cursor, value, sizeof(value)))
            return false;
        strncpy(out, value, out_size - 1);
        out[out_size - 1] = '\0';
        return true;
    }
    return false;
}
