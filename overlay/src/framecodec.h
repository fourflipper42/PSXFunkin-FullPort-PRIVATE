#ifndef FRAMECODEC_H
#define FRAMECODEC_H
/* No heap allocation and no PS1-specific dependencies: test on the host too. */
int FrameCodec_Decode(const unsigned char *src, unsigned int src_size,
                      unsigned char *dst, unsigned int dst_size);
typedef struct {
    unsigned int width, height, frames, size;
} FrameCodecInfo;
int FrameCodec_Open(const unsigned char *data, unsigned int size, FrameCodecInfo *info);
int FrameCodec_Frame(const unsigned char *data, unsigned int size, unsigned int frame,
                     unsigned char *dst, unsigned int capacity);
#endif
