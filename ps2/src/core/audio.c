#include "audio.h"

#include <audsrv.h>
#include <loadfile.h>
#include <sbv_patches.h>
#include <stdio.h>

extern unsigned char audsrv_irx[] __attribute__((aligned(16)));
extern unsigned int size_audsrv_irx;

static boolean audio_ready;
static u64 submitted_frames;

boolean Audio_Init(void)
{
    struct audsrv_fmt_t format;
    int ret;
    int modres = 0;

    audio_ready = false;
    submitted_frames = 0;

    ret = SifLoadModule("rom0:LIBSD", 0, NULL);
    if (ret < 0) {
        printf("[PS2] LIBSD load failed: %d\n", ret);
        return false;
    }

    /* Allow loading the bundled IOP module directly from EE memory. */
    sbv_patch_enable_lmb();
    ret = SifExecModuleBuffer(audsrv_irx, size_audsrv_irx, 0, NULL, &modres);
    if (ret < 0) {
        printf("[PS2] audsrv.irx load failed: %d (%d)\n", ret, modres);
        return false;
    }

    ret = audsrv_init();
    if (ret != AUDSRV_ERR_NOERROR) {
        printf("[PS2] audsrv_init failed: %s\n", audsrv_get_error_string());
        return false;
    }

    format.freq = AUDIO_SAMPLE_RATE;
    format.bits = AUDIO_BITS;
    format.channels = AUDIO_CHANNELS;
    ret = audsrv_set_format(&format);
    if (ret != AUDSRV_ERR_NOERROR) {
        printf("[PS2] audsrv format failed: %s\n", audsrv_get_error_string());
        audsrv_quit();
        return false;
    }

    audsrv_set_volume(MAX_VOLUME);
    audio_ready = true;
    printf("[PS2] audsrv initialized: %d Hz, %d-bit stereo\n",
        AUDIO_SAMPLE_RATE, AUDIO_BITS);
    return true;
}

boolean Audio_Ready(void)
{
    return audio_ready;
}

int Audio_AvailableBytes(void)
{
    if (!audio_ready)
        return 0;
    return audsrv_available();
}

int Audio_QueuedBytes(void)
{
    if (!audio_ready)
        return 0;
    return audsrv_queued();
}

int Audio_QueuePCM(const void *pcm, size_t bytes)
{
    int available;
    int queued;

    if (!audio_ready || pcm == NULL || bytes < AUDIO_FRAME_BYTES)
        return 0;

    available = audsrv_available();
    if (available <= 0)
        return 0;

    if (bytes > (size_t)available)
        bytes = (size_t)available;

    /* Never split a signed-16 stereo sample frame. */
    bytes &= ~(size_t)(AUDIO_FRAME_BYTES - 1);
    if (bytes == 0)
        return 0;

    queued = audsrv_play_audio((const char *)pcm, (int)bytes);
    if (queued > 0)
        submitted_frames += (u64)queued / AUDIO_FRAME_BYTES;
    return queued;
}

u64 Audio_SubmittedFrames(void)
{
    return submitted_frames;
}

u64 Audio_PlayedFrames(void)
{
    u64 queued_frames;

    if (!audio_ready)
        return 0;

    queued_frames = (u64)Audio_QueuedBytes() / AUDIO_FRAME_BYTES;
    if (queued_frames >= submitted_frames)
        return 0;
    return submitted_frames - queued_frames;
}

fixed_t Audio_PlayedSeconds(void)
{
    u64 frames = Audio_PlayedFrames();
    return (fixed_t)((frames << FIXED_SHIFT) / AUDIO_SAMPLE_RATE);
}

void Audio_Stop(void)
{
    if (!audio_ready)
        return;
    audsrv_stop_audio();
    submitted_frames = 0;
}

void Audio_Shutdown(void)
{
    if (!audio_ready)
        return;
    audsrv_stop_audio();
    audsrv_quit();
    audio_ready = false;
    submitted_frames = 0;
}
