#ifndef FNF_PS2_NOTE_KINDS_H
#define FNF_PS2_NOTE_KINDS_H

#include "fixed.h"
#include <stddef.h>

typedef struct NoteKindRecord {
    u32 name_offset;
    u32 params_offset;
} __attribute__((packed)) NoteKindRecord;

typedef struct NoteKindEntry {
    const char *name;
    const char *params_json;
} NoteKindEntry;

typedef struct NoteKindTable {
    void *blob;
    size_t blob_size;
    NoteKindRecord *records;
    char *strings;
    u32 string_bytes;
    u16 count;
    boolean loaded;
} NoteKindTable;

boolean NoteKinds_Load(NoteKindTable *table, const char *path);
void NoteKinds_Free(NoteKindTable *table);
boolean NoteKinds_Get(const NoteKindTable *table, u8 index, NoteKindEntry *entry);
boolean NoteKinds_NameEquals(const NoteKindTable *table, u8 index, const char *name);
boolean NoteKinds_ParamString(
    const NoteKindTable *table,
    u8 index,
    const char *param_name,
    char *out,
    size_t out_size);

#endif
