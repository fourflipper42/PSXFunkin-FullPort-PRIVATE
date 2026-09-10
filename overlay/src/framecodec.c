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
