#ifndef FNF_PS2_AUDIO_H
#define FNF_PS2_AUDIO_H

#include "psx.h"
#include <stddef.h>

#define AUDIO_SAMPLE_RATE 48000
#define AUDIO_CHANNELS 2
#define AUDIO_BITS 16
#define AUDIO_FRAME_BYTES 4

boolean Audio_Init(void);
boolean Audio_Ready(void);
int Audio_AvailableBytes(void);
int Audio_QueuedBytes(void);
int Audio_QueuePCM(const void *pcm, size_t bytes);
u64 Audio_SubmittedFrames(void);
u64 Audio_PlayedFrames(void);
fixed_t Audio_PlayedSeconds(void);
void Audio_Stop(void);
void Audio_Shutdown(void);

#endif
