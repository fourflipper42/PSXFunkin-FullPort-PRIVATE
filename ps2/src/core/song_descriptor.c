#include "song_descriptor.h"

#include "asset_file.h"
#include "mem.h"
#include <ctype.h>
#include <stdio.h>
#include <string.h>

typedef struct SongDescriptorHeader {
    char magic[4];
    u16 version;
    u16 flags;
    u32 string_bytes;
    u32 song_id_offset;
    u32 display_name_offset;
    u32 variation_offset;
    u32 difficulty_offset;
    u32 stage_offset;
    u32 note_style_offset;
    u32 player_offset;
    u32 girlfriend_offset;
    u32 opponent_offset;
    u32 instrumental_offset;
    float scroll_speed;
} __attribute__((packed)) SongDescriptorHeader;

#define SONG_DESCRIPTOR_VERSION 1
#define SONG_NO_STRING 0xFFFFFFFFu

static const char *descriptor_string(const SongDescriptor *song, u32 offset)
{
    const char *value;
    size_t remaining;
    if (song == NULL || song->strings == NULL || offset == SONG_NO_STRING ||
        offset >= song->string_bytes)
        return "";
    value = song->strings + offset;
    remaining = song->string_bytes - offset;
    if (memchr(value, '\0', remaining) == NULL)
        return NULL;
    return value;
}

static void uppercase_path(char *path)
{
    unsigned char *p = (unsigned char *)path;
    while (*p != '\0') {
        *p = (unsigned char)toupper(*p);
        ++p;
    }
}

static boolean format_path(char *out, size_t out_size, const char *format,
    const char *a, const char *b, const char *c)
{
    int written = snprintf(out, out_size, format,
        a != NULL ? a : "",
        b != NULL ? b : "",
        c != NULL ? c : "");
    if (written < 0 || (size_t)written >= out_size)
        return false;
    uppercase_path(out);
    return true;
}

boolean SongDescriptor_Load(SongDescriptor *song, const char *path)
{
    AssetFile file;
    SongDescriptorHeader *header;
    size_t got;
    const char *values[10];
    u32 offsets[10];
    int i;

    if (song == NULL || path == NULL)
        return false;

    memset(song, 0, sizeof(*song));
    memset(&file, 0, sizeof(file));
    if (!AssetFile_Open(&file, path))
        return false;

    song->blob_size = AssetFile_Size(&file);
    if (song->blob_size < sizeof(SongDescriptorHeader))
        goto fail;

    song->blob = Mem_Alloc(song->blob_size);
    if (song->blob == NULL)
        goto fail;
    got = AssetFile_Read(&file, song->blob, song->blob_size);
    AssetFile_Close(&file);
    if (got != song->blob_size)
        goto fail;

    header = (SongDescriptorHeader *)song->blob;
    if (memcmp(header->magic, "FSON", 4) != 0 ||
        header->version != SONG_DESCRIPTOR_VERSION ||
        sizeof(SongDescriptorHeader) + (size_t)header->string_bytes > song->blob_size)
        goto fail;

    song->strings = (char *)song->blob + sizeof(SongDescriptorHeader);
    song->string_bytes = header->string_bytes;

    offsets[0] = header->song_id_offset;
    offsets[1] = header->display_name_offset;
    offsets[2] = header->variation_offset;
    offsets[3] = header->difficulty_offset;
    offsets[4] = header->stage_offset;
    offsets[5] = header->note_style_offset;
    offsets[6] = header->player_offset;
    offsets[7] = header->girlfriend_offset;
    offsets[8] = header->opponent_offset;
    offsets[9] = header->instrumental_offset;
    for (i = 0; i < 10; ++i) {
        values[i] = descriptor_string(song, offsets[i]);
        if (values[i] == NULL)
            goto fail;
    }

    song->song_id = values[0];
    song->display_name = values[1];
    song->variation = values[2];
    song->difficulty = values[3];
    song->stage = values[4];
    song->note_style = values[5];
    song->player = values[6];
    song->girlfriend = values[7];
    song->opponent = values[8];
    song->instrumental = values[9];
    song->scroll_speed = (fixed_t)(header->scroll_speed * (float)FIXED_UNIT);
    if (song->scroll_speed <= 0)
        song->scroll_speed = FIXED_UNIT;
    song->loaded = true;
    return true;

fail:
    AssetFile_Close(&file);
    SongDescriptor_Free(song);
    return false;
}

void SongDescriptor_Free(SongDescriptor *song)
{
    if (song == NULL)
        return;
    if (song->blob != NULL)
        Mem_Free(song->blob);
    memset(song, 0, sizeof(*song));
}

boolean SongDescriptor_BuildDiscPaths(const SongDescriptor *song, SongAssetPaths *paths)
{
    if (song == NULL || !song->loaded || paths == NULL ||
        song->song_id == NULL || song->variation == NULL || song->difficulty == NULL)
        return false;

    memset(paths, 0, sizeof(*paths));
    if (!format_path(paths->chart, sizeof(paths->chart),
        "\\CHART\\%s\\%s\\%s.CHT;1",
        song->song_id, song->variation, song->difficulty))
        return false;
    if (!format_path(paths->inst, sizeof(paths->inst),
        "\\AUDIO\\%s\\%s\\INST.PCM;1",
        song->song_id, song->variation, ""))
        return false;
    if (!format_path(paths->voices, sizeof(paths->voices),
        "\\AUDIO\\%s\\%s\\VOICES.PCM;1",
        song->song_id, song->variation, ""))
        return false;
    if (!format_path(paths->stage_base, sizeof(paths->stage_base),
        "\\GAME\\STAGE\\%s", song->stage, "", ""))
        return false;
    if (!format_path(paths->player_base, sizeof(paths->player_base),
        "\\GAME\\CHAR\\%s", song->player, "", ""))
        return false;
    if (song->girlfriend != NULL && song->girlfriend[0] != '\0') {
        if (!format_path(paths->girlfriend_base, sizeof(paths->girlfriend_base),
            "\\GAME\\CHAR\\%s", song->girlfriend, "", ""))
            return false;
    }
    if (!format_path(paths->opponent_base, sizeof(paths->opponent_base),
        "\\GAME\\CHAR\\%s", song->opponent, "", ""))
        return false;
    return true;
}

void SongDescriptor_CharacterFile(
    char *out,
    size_t out_size,
    const char *character_base,
    const char *filename)
{
    int written;
    if (out == NULL || out_size == 0)
        return;
    out[0] = '\0';
    if (character_base == NULL || character_base[0] == '\0' || filename == NULL)
        return;
    written = snprintf(out, out_size, "%s\\%s;1", character_base, filename);
    if (written < 0 || (size_t)written >= out_size) {
        out[0] = '\0';
        return;
    }
    uppercase_path(out);
}
