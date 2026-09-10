#ifndef FRAMECODEC_H
#define FRAMECODEC_H
/* No heap allocation and no PS1-specific dependencies: test on the host too. */
int FrameCodec_Decode(const unsigned char *src, unsigned int src_size,
                      unsigned char *dst, unsigned int dst_size);
#endif
