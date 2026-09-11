#include "framebank.h"
#include "mem.h"
#include "main.h"
/* Shared, word-aligned upload buffer; no per-frame allocation. Gfx_LoadTex
   waits for each DMA transfer before another bank reuses this buffer. */
static u32 upload_buffer[(65536 + 544) / 4];

static void Fail(const char *message)
{
    sprintf(error_msg, "[FrameBank] %s", message);
    ErrorLock();
}
static void Write16(u8 *p, u16 value) { p[0] = value; p[1] = value >> 8; }
static void Write32(u8 *p, u32 value)
{
    p[0] = value; p[1] = value >> 8; p[2] = value >> 16; p[3] = value >> 24;
}
void FrameBank_Load(FrameBank *bank, const char *path, u16 x, u16 y, u16 clut_x, u16 clut_y)
{
    CdlFILE file;
    memset(bank, 0, sizeof(*bank));
    IO_FindFile(&file, path);
    bank->data = IO_ReadFile(&file);
    if (!FrameCodec_Open((u8*)bank->data, file.size, &bank->info)) Fail("invalid bank");
    if ((x & 63) || (y & 255) || x + bank->info.width / 2 > 1024 ||
        y + bank->info.height > 512 || (clut_x & 15) || clut_x + 256 > 1024 || clut_y >= 512)
        Fail("invalid VRAM placement");
    bank->x = x; bank->y = y; bank->clut_x = clut_x; bank->clut_y = clut_y;
    bank->frame = 0xFFFF;
}
void FrameBank_Free(FrameBank *bank)
{
    Mem_Free(bank->data);
    bank->data = NULL;
    bank->frame = 0xFFFF;
}
void FrameBank_Invalidate(FrameBank *bank) { bank->frame = 0xFFFF; }
void FrameBank_Upload(FrameBank *bank, u16 frame)
{
    u8 *tim = (u8*)upload_buffer;
    u32 pixels = bank->info.width * bank->info.height;
    if (frame == bank->frame) return;
    /* Duplicate timeline entries share one payload. Keep their timing without
       decoding/uploading identical pixels again. Both indices must be valid. */
    if (frame < bank->info.frames && bank->frame < bank->info.frames &&
        !memcmp((u8*)bank->data + 528 + frame * 8,
                (u8*)bank->data + 528 + bank->frame * 8, 8)) {
        bank->frame = frame;
        return;
    }
    if (!FrameCodec_Frame((u8*)bank->data, bank->info.size, frame, tim + 544, 65536))
        Fail("invalid frame");
    Write32(tim, 0x10); Write32(tim + 4, 9);
    Write32(tim + 8, 524);
    Write16(tim + 12, bank->clut_x); Write16(tim + 14, bank->clut_y);
    Write16(tim + 16, 256); Write16(tim + 18, 1);
    memcpy(tim + 20, (u8*)bank->data + 16, 512);
    Write32(tim + 532, pixels + 12);
    Write16(tim + 536, bank->x); Write16(tim + 538, bank->y);
    Write16(tim + 540, bank->info.width / 2); Write16(tim + 542, bank->info.height);
    Gfx_LoadTex(&bank->texture, upload_buffer, 0);
    bank->frame = frame;
}
void FrameBank_Draw(FrameBank *bank, u16 frame, s16 x, s16 y)
{
    RECT src = {0, 0, bank->info.width, bank->info.height};
    FrameBank_Upload(bank, frame);
    Gfx_BlitTex(&bank->texture, &src, x, y);
}
