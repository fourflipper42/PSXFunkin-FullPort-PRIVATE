#include "cutscene_stream.h"

#include "asset_file.h"
#include <stdio.h>
#include <string.h>

typedef struct CutsceneHeader {
    char magic[4];
    u16 version;
    u16 flags;
    u16 width;
    u16 height;
    u16 fps_num;
    u16 fps_den;
    u32 frame_count;
    u16 columns;
    u16 rows;
    u16 page_count;
    u16 reserved;
} __attribute__((packed)) CutsceneHeader;

#define CUTSCENE_VERSION 1
#define CUTSCENE_NO_PAGE 0xFFFFu

static boolean is_disc_path(const char *path)
{
    return path != NULL && (path[0] == '\\' || strncmp(path, "cdrom0:", 7) == 0);
}

static void cutscene_path(
    char *out,
    size_t out_size,
    const char *base,
    const char *leaf)
{
    char separator;
    size_t len;
    boolean disc;

    if (out == NULL || out_size == 0) return;
    out[0] = '\0';
    if (base == NULL || leaf == NULL) return;
    disc = is_disc_path(base);
    separator = disc ? '\\' : '/';
    len = strlen(base);
    if (len != 0 && (base[len - 1] == '/' || base[len - 1] == '\\'))
        snprintf(out, out_size, "%s%s%s", base, leaf, disc ? ";1" : "");
    else
        snprintf(out, out_size, "%s%c%s%s", base, separator, leaf, disc ? ";1" : "");
}

static boolean load_page(GSGLOBAL *gs, CutsceneStream *stream, u16 page)
{
    char leaf[32];
    char path[320];

    if (gs == NULL || stream == NULL || page >= stream->page_count)
        return false;
    if (stream->page_loaded && stream->loaded_page == page)
        return true;

    if (stream->page_loaded)
        TextureAsset_Forget(&stream->page);
    stream->page_loaded = false;
    stream->loaded_page = CUTSCENE_NO_PAGE;

    snprintf(leaf, sizeof(leaf), "P%03u.FPTX", (unsigned)page);
    cutscene_path(path, sizeof(path), stream->base_path, leaf);
    if (!TextureAsset_Load(gs, &stream->page, path, true)) {
        printf("[PS2] cutscene page load failed: %s\n", path);
        return false;
    }
    stream->page_loaded = true;
    stream->loaded_page = page;
    return true;
}

boolean CutsceneStream_Open(
    GSGLOBAL *gs,
    CutsceneStream *stream,
    const char *base_path)
{
    AssetFile file;
    CutsceneHeader header;
    char config_path[320];
    char audio_path[320];
    u32 frames_per_page;

    if (gs == NULL || stream == NULL || base_path == NULL || base_path[0] == '\0')
        return false;

    memset(stream, 0, sizeof(*stream));
    memset(&file, 0, sizeof(file));
    stream->loaded_page = CUTSCENE_NO_PAGE;
    strncpy(stream->base_path, base_path, sizeof(stream->base_path) - 1);
    stream->base_path[sizeof(stream->base_path) - 1] = '\0';

    cutscene_path(config_path, sizeof(config_path), base_path, "CUT.FCUT");
    if (!AssetFile_Open(&file, config_path))
        return false;
    if (AssetFile_Read(&file, &header, sizeof(header)) != sizeof(header)) {
        AssetFile_Close(&file);
        return false;
    }
    AssetFile_Close(&file);

    frames_per_page = (u32)header.columns * (u32)header.rows;
    if (memcmp(header.magic, "FCUT", 4) != 0 ||
        header.version != CUTSCENE_VERSION ||
        header.width == 0 || header.height == 0 ||
        header.fps_num == 0 || header.fps_den == 0 ||
        header.frame_count == 0 || header.columns == 0 || header.rows == 0 ||
        frames_per_page == 0 || header.page_count == 0 ||
        ((header.frame_count + frames_per_page - 1u) / frames_per_page) != header.page_count)
        return false;

    stream->width = header.width;
    stream->height = header.height;
    stream->fps_num = header.fps_num;
    stream->fps_den = header.fps_den;
    stream->frame_count = header.frame_count;
    stream->columns = header.columns;
    stream->rows = header.rows;
    stream->page_count = header.page_count;
    stream->frame_index = 0;

    cutscene_path(audio_path, sizeof(audio_path), base_path, "AUDIO.PCM");
    if (!SongStream_Open(&stream->audio, audio_path, NULL))
        return false;
    if (!load_page(gs, stream, 0)) {
        SongStream_Close(&stream->audio);
        return false;
    }

    stream->loaded = true;
    stream->finished = false;
    printf("[PS2] cutscene loaded: %ux%u %u/%u fps, %u frames, %u pages\n",
        (unsigned)stream->width,
        (unsigned)stream->height,
        (unsigned)stream->fps_num,
        (unsigned)stream->fps_den,
        (unsigned)stream->frame_count,
        (unsigned)stream->page_count);
    return true;
}

void CutsceneStream_Close(CutsceneStream *stream)
{
    if (stream == NULL)
        return;
    if (stream->page_loaded)
        TextureAsset_Forget(&stream->page);
    SongStream_Close(&stream->audio);
    memset(stream, 0, sizeof(*stream));
    stream->loaded_page = CUTSCENE_NO_PAGE;
}

void CutsceneStream_Tick(GSGLOBAL *gs, CutsceneStream *stream)
{
    fixed_t seconds;
    u64 scaled;
    u32 frame;
    u32 frames_per_page;
    u16 page;

    if (gs == NULL || stream == NULL || !stream->loaded || stream->finished)
        return;

    SongStream_Tick(&stream->audio);
    seconds = SongStream_PlayedSeconds(&stream->audio);
    scaled = (u64)(u32)seconds * (u64)stream->fps_num;
    frame = (u32)(scaled / ((u64)stream->fps_den << FIXED_SHIFT));
    if (frame >= stream->frame_count) {
        frame = stream->frame_count - 1u;
        if (SongStream_Finished(&stream->audio))
            stream->finished = true;
    }

    stream->frame_index = frame;
    frames_per_page = (u32)stream->columns * (u32)stream->rows;
    page = (u16)(frame / frames_per_page);
    if (!load_page(gs, stream, page))
        stream->finished = true;
}

boolean CutsceneStream_SetPaused(CutsceneStream *stream, boolean paused)
{
    if (stream == NULL || !stream->loaded || stream->finished)
        return false;
    if (paused)
        return SongStream_Pause(&stream->audio);
    return SongStream_Resume(&stream->audio);
}

boolean CutsceneStream_Finished(const CutsceneStream *stream)
{
    return stream == NULL || !stream->loaded || stream->finished;
}

void CutsceneStream_Draw(
    GSGLOBAL *gs,
    const CutsceneStream *stream,
    int z,
    u64 color)
{
    u32 frames_per_page;
    u32 local;
    u32 column;
    u32 row;
    float u1;
    float v1;
    float u2;
    float v2;

    if (gs == NULL || stream == NULL || !stream->loaded || !stream->page_loaded)
        return;

    frames_per_page = (u32)stream->columns * (u32)stream->rows;
    local = stream->frame_index % frames_per_page;
    column = local % stream->columns;
    row = local / stream->columns;
    u1 = (float)(column * stream->width);
    v1 = (float)(row * stream->height);
    u2 = u1 + (float)stream->width;
    v2 = v1 + (float)stream->height;

    TextureAsset_Draw(
        gs,
        &stream->page,
        0.0f, 0.0f,
        640.0f, 360.0f,
        u1, v1, u2, v2,
        z, color);
}
