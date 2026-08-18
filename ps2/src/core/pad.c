#include "pad.h"

#include <stdio.h>
#include <string.h>
#include <loadfile.h>

static char pad_buffer[256] __attribute__((aligned(64)));
static boolean pad_ready;
Pad pad_state;

static void Pad_ResetState(void)
{
    pad_state.held = 0;
    pad_state.press = 0;
    pad_state.left_x = 0x80;
    pad_state.left_y = 0x80;
    pad_state.right_x = 0x80;
    pad_state.right_y = 0x80;
}

void Pad_Init(void)
{
    int ret;

    pad_ready = false;
    Pad_ResetState();
    memset(pad_buffer, 0, sizeof(pad_buffer));

    ret = SifLoadModule("rom0:SIO2MAN", 0, NULL);
    if (ret < 0) {
        printf("[PS2] SIO2MAN load failed: %d\n", ret);
        return;
    }

    ret = SifLoadModule("rom0:PADMAN", 0, NULL);
    if (ret < 0) {
        printf("[PS2] PADMAN load failed: %d\n", ret);
        return;
    }

    if (!padInit(0)) {
        printf("[PS2] padInit failed\n");
        return;
    }

    if (!padPortOpen(0, 0, pad_buffer)) {
        printf("[PS2] padPortOpen failed\n");
        return;
    }

    padSetMainMode(0, 0, PAD_MMODE_DUALSHOCK, PAD_MMODE_LOCK);
    pad_ready = true;
    printf("[PS2] DualShock 2 initialized\n");
}

void Pad_Update(void)
{
    struct padButtonStatus status;
    u16 previous;
    int state;

    previous = pad_state.held;
    pad_state.press = 0;

    if (!pad_ready)
        return;

    state = padGetState(0, 0);
    if (state != PAD_STATE_STABLE && state != PAD_STATE_FINDCTP1) {
        pad_state.held = 0;
        return;
    }

    memset(&status, 0, sizeof(status));
    if (!padRead(0, 0, &status)) {
        pad_state.held = 0;
        return;
    }

    pad_state.held = (u16)(0xFFFFu ^ status.btns);
    pad_state.press = (u16)(pad_state.held & (u16)~previous);
    pad_state.left_x = status.ljoy_h;
    pad_state.left_y = status.ljoy_v;
    pad_state.right_x = status.rjoy_h;
    pad_state.right_y = status.rjoy_v;
}

boolean Pad_Ready(void)
{
    return pad_ready;
}
