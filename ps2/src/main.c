#include <stdio.h>
#include <string.h>
#include <kernel.h>
#include <sifrpc.h>
#include <loadfile.h>
#include <libpad.h>
#include <tamtypes.h>

#include <gsKit.h>
#include <dmaKit.h>

#define LOGICAL_W 640.0f
#define LOGICAL_H 360.0f
#define NTSC_W    640.0f
#define NTSC_H    448.0f

/*
 * FNF PS2 uses one canonical 640x360 logical layout.
 *
 * WIDE_ANAMORPHIC:
 *   The 640x360 scene fills the 640x448 NTSC raster. A TV set to 16:9
 *   stretches the 4:3 raster horizontally, producing the intended 16:9 image.
 *
 * LETTERBOX_4_3:
 *   The same scene occupies 640x336 inside the 640x448 raster, leaving
 *   56-line black bars above and below. This preserves the same composition
 *   on a 4:3 television without maintaining a second UI layout.
 */
typedef enum AspectMode {
    ASPECT_WIDE_ANAMORPHIC = 0,
    ASPECT_LETTERBOX_4_3 = 1
} AspectMode;

typedef struct VideoTransform {
    float x_scale;
    float y_scale;
    float x_offset;
    float y_offset;
} VideoTransform;

static char g_pad_buf[256] __attribute__((aligned(64)));
static u32 g_buttons = 0;
static u32 g_buttons_prev = 0;
static int g_pad_ready = 0;

static VideoTransform video_transform(AspectMode mode)
{
    VideoTransform t;
    t.x_scale = NTSC_W / LOGICAL_W;
    t.x_offset = 0.0f;

    if (mode == ASPECT_LETTERBOX_4_3) {
        const float content_h = NTSC_H * 0.75f; /* 336 lines */
        t.y_scale = content_h / LOGICAL_H;
        t.y_offset = (NTSC_H - content_h) * 0.5f;
    } else {
        t.y_scale = NTSC_H / LOGICAL_H;
        t.y_offset = 0.0f;
    }

    return t;
}

static float video_x(const VideoTransform *t, float x)
{
    return t->x_offset + (x * t->x_scale);
}

static float video_y(const VideoTransform *t, float y)
{
    return t->y_offset + (y * t->y_scale);
}

static void draw_logical_rect(
    GSGLOBAL *gs,
    const VideoTransform *t,
    float x1,
    float y1,
    float x2,
    float y2,
    int z,
    u64 color)
{
    gsKit_prim_sprite(
        gs,
        video_x(t, x1), video_y(t, y1),
        video_x(t, x2), video_y(t, y2),
        z,
        color);
}

static int init_pad(void)
{
    int ret;

    ret = SifLoadModule("rom0:SIO2MAN", 0, NULL);
    if (ret < 0) {
        printf("[PS2] SIO2MAN load failed: %d\n", ret);
        return 0;
    }

    ret = SifLoadModule("rom0:PADMAN", 0, NULL);
    if (ret < 0) {
        printf("[PS2] PADMAN load failed: %d\n", ret);
        return 0;
    }

    if (!padInit(0)) {
        printf("[PS2] padInit failed\n");
        return 0;
    }

    if (!padPortOpen(0, 0, g_pad_buf)) {
        printf("[PS2] padPortOpen failed\n");
        return 0;
    }

    padSetMainMode(0, 0, PAD_MMODE_DUALSHOCK, PAD_MMODE_LOCK);
    printf("[PS2] DualShock 2 initialized\n");
    return 1;
}

static void update_pad(void)
{
    struct padButtonStatus status;
    int state;

    g_buttons_prev = g_buttons;
    g_buttons = 0;

    if (!g_pad_ready)
        return;

    state = padGetState(0, 0);
    if (state != PAD_STATE_STABLE && state != PAD_STATE_FINDCTP1)
        return;

    memset(&status, 0, sizeof(status));
    if (padRead(0, 0, &status))
        g_buttons = 0xFFFFu ^ status.btns;
}

static int button_pressed(u32 button)
{
    return ((g_buttons & button) != 0) && ((g_buttons_prev & button) == 0);
}

static GSGLOBAL *init_video(void)
{
    GSGLOBAL *gs = gsKit_init_global();

    gs->Mode = GS_MODE_NTSC;
    gs->Interlace = GS_INTERLACED;
    gs->Field = GS_FRAME;
    gs->Width = (int)NTSC_W;
    gs->Height = (int)NTSC_H;
    gs->PSM = GS_PSM_CT16;
    gs->PSMZ = GS_PSMZ_16S;
    gs->ZBuffering = GS_SETTING_OFF;
    gs->DoubleBuffering = GS_SETTING_ON;
    gs->PrimAlphaEnable = GS_SETTING_ON;

    dmaKit_init(
        D_CTRL_RELE_OFF,
        D_CTRL_MFD_OFF,
        D_CTRL_STS_UNSPEC,
        D_CTRL_STD_OFF,
        D_CTRL_RCYC_8,
        1 << DMA_CHANNEL_GIF);
    dmaKit_chan_init(DMA_CHANNEL_GIF);

    gsKit_init_screen(gs);
    gsKit_mode_switch(gs, GS_ONESHOT);

    printf("[PS2] GS initialized: %dx%d NTSC\n", gs->Width, gs->Height);
    return gs;
}

static void render_boot_test(GSGLOBAL *gs, AspectMode aspect)
{
    const u64 black = GS_SETREG_RGBAQ(0x00, 0x00, 0x00, 0x80, 0x00);
    const u64 bg = GS_SETREG_RGBAQ(0x18, 0x18, 0x2c, 0x80, 0x00);
    const u64 white = GS_SETREG_RGBAQ(0xff, 0xff, 0xff, 0x80, 0x00);
    const u64 lane_a = GS_SETREG_RGBAQ(0x44, 0x44, 0x72, 0x80, 0x00);
    const u64 lane_b = GS_SETREG_RGBAQ(0x62, 0x62, 0x96, 0x80, 0x00);
    VideoTransform t = video_transform(aspect);
    int i;

    gsKit_clear(gs, black);

    /* Canonical 16:9 content area. Black outside it becomes the 4:3 bars. */
    draw_logical_rect(gs, &t, 0.0f, 0.0f, 640.0f, 360.0f, 1, bg);

    /* Visible safe-frame markers for the first hardware/emulator test. */
    draw_logical_rect(gs, &t, 16.0f, 16.0f, 624.0f, 18.0f, 2, white);
    draw_logical_rect(gs, &t, 16.0f, 342.0f, 624.0f, 344.0f, 2, white);
    draw_logical_rect(gs, &t, 16.0f, 16.0f, 18.0f, 344.0f, 2, white);
    draw_logical_rect(gs, &t, 622.0f, 16.0f, 624.0f, 344.0f, 2, white);

    /* Four FNF note-lane placeholders. These get replaced by the real HUD next. */
    for (i = 0; i < 4; ++i) {
        float x1 = 224.0f + (i * 52.0f);
        float x2 = x1 + 44.0f;
        draw_logical_rect(gs, &t, x1, 42.0f, x2, 318.0f, 2, (i & 1) ? lane_b : lane_a);
        draw_logical_rect(gs, &t, x1, 54.0f, x2, 58.0f, 3, white);
    }

    /* Aspect indicator: wide bar = 16:9, short bar = 4:3 letterbox. */
    if (aspect == ASPECT_WIDE_ANAMORPHIC)
        draw_logical_rect(gs, &t, 32.0f, 320.0f, 176.0f, 328.0f, 3, white);
    else
        draw_logical_rect(gs, &t, 32.0f, 320.0f, 104.0f, 328.0f, 3, white);

    gsKit_queue_exec(gs);
    gsKit_sync_flip(gs);
}

int main(int argc, char **argv)
{
    GSGLOBAL *gs;
    AspectMode aspect = ASPECT_WIDE_ANAMORPHIC;

    (void)argc;
    (void)argv;

    printf("\nFNF PS2 native port bootstrap\n");
    printf("logical canvas: 640x360\n");
    printf("TRIANGLE: toggle 16:9 / 4:3 letterbox\n");

    SifInitRpc(0);
    g_pad_ready = init_pad();
    gs = init_video();

    for (;;) {
        update_pad();

        if (button_pressed(PAD_TRIANGLE)) {
            aspect = (aspect == ASPECT_WIDE_ANAMORPHIC)
                ? ASPECT_LETTERBOX_4_3
                : ASPECT_WIDE_ANAMORPHIC;
            printf("[PS2] aspect = %s\n",
                aspect == ASPECT_WIDE_ANAMORPHIC ? "16:9 anamorphic" : "4:3 letterbox");
        }

        render_boot_test(gs, aspect);
    }

    return 0;
}
