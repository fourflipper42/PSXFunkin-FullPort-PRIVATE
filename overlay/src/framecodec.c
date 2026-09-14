#include "framecodec.h"
int FrameCodec_Decode(const unsigned char *src, unsigned int src_size,
                      unsigned char *dst, unsigned int dst_size)
{
    unsigned int input = 0, output = 0;
    if (!src || !dst) return 0;
    while (input < src_size)
    {
        unsigned int command = src[input++];
        unsigned int count = (command & 127) + 1;
        if (count > dst_size - output) return 0;
        if (command & 128)
        {
            unsigned char value;
            if (input == src_size) return 0;
            value = src[input++];
            while (count--) dst[output++] = value;
        }
        else
        {
            if (count > src_size - input) return 0;
            while (count--) dst[output++] = src[input++];
        }
    }
    return output == dst_size;
}

static unsigned int Read16(const unsigned char *p)
{
    return p[0] | ((unsigned int)p[1] << 8);
}
static unsigned int Read32(const unsigned char *p)
{
    return p[0] | ((unsigned int)p[1] << 8) |
           ((unsigned int)p[2] << 16) | ((unsigned int)p[3] << 24);
}
static int BankHeader(const unsigned char *data, unsigned int size, FrameCodecInfo *info)
{
    if (!data || !info || size < 528) return 0;
    if (data[0] != 'F' || data[1] != 'B' || data[2] != 'K' || data[3] != '1') return 0;
    info->size = Read32(data + 4);
    info->width = Read16(data + 8);
    info->height = Read16(data + 10);
    info->frames = Read16(data + 12);
    return info->size == size && info->width && info->width <= 256 &&
           !(info->width & 1) && info->height && info->height <= 256 &&
           info->frames && Read16(data + 14) == 256 &&
           528 + info->frames * 8 <= size;
}
static int FrameRange(const unsigned char *data, unsigned int size,
                      unsigned int frame, unsigned int count,
                      unsigned int *offset, unsigned int *length)
{
    const unsigned char *entry;
    if (frame >= count) return 0;
    entry = data + 528 + frame * 8;
    *offset = Read32(entry);
    *length = Read32(entry + 4);
    return *offset >= 528 + count * 8 && *offset <= size && *length &&
           *length <= size - *offset;
}
int FrameCodec_Open(const unsigned char *data, unsigned int size, FrameCodecInfo *info)
{
    unsigned int i, offset, length;
    if (!BankHeader(data, size, info)) return 0;
    for (i = 0; i < info->frames; i++)
        if (!FrameRange(data, size, i, info->frames, &offset, &length)) return 0;
    return 1;
}
int FrameCodec_Frame(const unsigned char *data, unsigned int size, unsigned int frame,
                     unsigned char *dst, unsigned int capacity)
{
    FrameCodecInfo info;
    unsigned int offset, length, pixels;
    if (!BankHeader(data, size, &info)) return 0;
    pixels = info.width * info.height;
    if (capacity < pixels || !FrameRange(data, size, frame, info.frames, &offset, &length)) return 0;
    return FrameCodec_Decode(data + offset, length, dst, pixels);
}
