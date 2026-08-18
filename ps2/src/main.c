#include <stdio.h>
#include <sifrpc.h>
#include <tamtypes.h>

#include <gsKit.h>
#include <dmaKit.h>

#include "core/timer.h"
#include "core/animation.h"
#include "core/pad.h"
#include "core/audio.h"
#include "core/disc.h"
#include "core/gameplay.h"

#define LOGICAL_W 640.0f
#define LOGICAL_H 360.0f
#define NTSC_W    640.0f
#define NTSC_H    448.0f

#define DEFAULT_CHART  "\\CHART\\TUTORIAL\\DEFAULT\\NORMAL.CHT;1"
#define DEFAULT_INST   "\\AUDIO\\TUTORIAL\\INST.PCM;1"
#define DEFAULT_VOICES "\\AUDIO\\TUTORIAL\\VOICES.PCM;1"

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

static u8 g_boot_anim_frame = 0;
static const u8 g_boot_anim_script[] = {
    0, 1, 2, 3, 2, 1, ASCR_REPEAT
};
static const Animation g_boot_anims[] = {
    {2, g_boot_anim_script}
};
static Animatable g_boot_anim;
static GameplayState g_gameplay;
static boolean g_gameplay_loaded;

static void boot_set_frame(void *user, u8 frame)
{
    u8 *out = (u8 *)user;
    *out = frame;
}

static VideoTransform video_transform(AspectMode mode)
{
    VideoTransform t;
    t.x_scale = NTSC_W / LOGICAL_W;
    t.x_offset = 0.0f;

    if (mode == ASPECT_LETTERBOX_4_3) {
        const float content_h = NTSC_H * 0.75f;
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
    float pulse_x;
    int i;

    gsKit_clear(gs, black);
    draw_logical_rect(gs, &t, 0.0f, 0.0f, 640.0f, 360.0f, 1, bg);

    draw_logical_rect(gs, &t, 16.0f, 16.0f, 624.0f, 18.0f, 2, white);
    draw_logical_rect(gs, &t, 16.0f, 342.0f, 624.0f, 344.0f, 2, white);
    draw_logical_rect(gs, &t, 16.0f, 16.0f, 18.0f, 344.0f, 2, white);
    draw_logical_rect(gs, &t, 622.0f, 16.0f, 624.0f, 344.0f, 2, white);

    for (i = 0; i < 4; ++i) {
        float x1 = 224.0f + (i * 52.0f);
        float x2 = x1 + 44.0f;
        draw_logical_rect(gs, &t, x1, 42.0f, x2, 318.0f, 2, (i & 1) ? lane_b : lane_a);
        draw_logical_rect(gs, &t, x1, 54.0f, x2, 58.0f, 3, white);
    }

    pulse_x = 238.0f + ((float)g_boot_anim_frame * 52.0f);
    draw_logical_rect(gs, &t, pulse_x, 286.0f, pulse_x + 16.0f, 302.0f, 4, white);

    gsKit_queue_exec(gs);
    gsKit_sync_flip(gs);
}

static u64 lane_color(u8 lane)
{
    switch (lane & 3) {
        case 0: return GS_SETREG_RGBAQ(0xc8, 0x6b, 0xff, 0x80, 0x00);
        case 1: return GS_SETREG_RGBAQ(0x4a, 0xc8, 0xff, 0x80, 0x00);
        case 2: return GS_SETREG_RGBAQ(0x61, 0xe8, 0x72, 0x80, 0x00);
        default: return GS_SETREG_RGBAQ(0xff, 0x5e, 0x67, 0x80, 0x00);
    }
}

static float lane_x(boolean opponent, u8 lane)
{
    return (opponent ? 72.0f : 392.0f) + ((float)(lane & 3) * 44.0f);
}

static void render_gameplay(GSGLOBAL *gs, AspectMode aspect, GameplayState *game)
{
    const u64 black = GS_SETREG_RGBAQ(0x00, 0x00, 0x00, 0x80, 0x00);
    const u64 bg = GS_SETREG_RGBAQ(0x1b, 0x16, 0x25, 0x80, 0x00);
    const u64 receptor = GS_SETREG_RGBAQ(0xe8, 0xe8, 0xe8, 0x80, 0x00);
    const u64 mine = GS_SETREG_RGBAQ(0x10, 0x10, 0x10, 0x80, 0x00);
    const u64 health_bg = GS_SETREG_RGBAQ(0x38, 0x38, 0x38, 0x80, 0x00);
    const u64 health_fg = GS_SETREG_RGBAQ(0xe8, 0xe8, 0xe8, 0x80, 0x00);
    const float receptor_y = 54.0f;
    VideoTransform t = video_transform(aspect);
    ChartView *chart = &game->chart.view;
    size_t i;
    int lane;
    float health_ratio;

    gsKit_clear(gs, black);
    draw_logical_rect(gs, &t, 0.0f, 0.0f, 640.0f, 360.0f, 1, bg);

    for (lane = 0; lane < 4; ++lane) {
        float ox = lane_x(true, (u8)lane);
        float px = lane_x(false, (u8)lane);
        draw_logical_rect(gs, &t, ox, receptor_y, ox + 30.0f, receptor_y + 30.0f, 4, receptor);
        draw_logical_rect(gs, &t, px, receptor_y, px + 30.0f, receptor_y + 30.0f, 4, receptor);
        draw_logical_rect(gs, &t, ox + 3.0f, receptor_y + 3.0f, ox + 27.0f, receptor_y + 27.0f, 5, bg);
        draw_logical_rect(gs, &t, px + 3.0f, receptor_y + 3.0f, px + 27.0f, receptor_y + 27.0f, 5, bg);
    }

    for (i = game->first_note; i < chart->note_count; ++i) {
        Note *note = &chart->notes[i];
        fixed_t delta;
        fixed_t pixel_delta;
        float y;
        float x;
        float w;
        float h;
        u64 color;

        if (note->type & NOTE_FLAG_HIT)
            continue;

        delta = Gameplay_NoteDelta(game, note);
        pixel_delta = FIXED_MUL(game->rhythm.note_speed, delta);
        y = receptor_y + ((float)pixel_delta / (float)FIXED_UNIT);
        if (y < -48.0f)
            continue;
        if (y > 390.0f)
            break;

        x = lane_x((note->type & NOTE_FLAG_OPPONENT) != 0, note->type & 3);
        color = (note->type & NOTE_FLAG_MINE) ? mine : lane_color(note->type & 3);
        if (note->type & NOTE_FLAG_SUSTAIN) {
            w = 12.0f;
            h = (note->type & NOTE_FLAG_SUSTAIN_END) ? 24.0f : 18.0f;
            x += 9.0f;
        } else {
            w = 30.0f;
            h = 30.0f;
        }
        draw_logical_rect(gs, &t, x, y, x + w, y + h, 3, color);
    }

    health_ratio = (float)game->rhythm.health / 20000.0f;
    if (health_ratio < 0.0f)
        health_ratio = 0.0f;
    if (health_ratio > 1.0f)
        health_ratio = 1.0f;
    draw_logical_rect(gs, &t, 170.0f, 330.0f, 470.0f, 340.0f, 5, health_bg);
    draw_logical_rect(gs, &t, 170.0f, 330.0f, 170.0f + 300.0f * health_ratio, 340.0f, 6, health_fg);

    gsKit_queue_exec(gs);
    gsKit_sync_flip(gs);
}

int main(int argc, char **argv)
{
    GSGLOBAL *gs;
    AspectMode aspect = ASPECT_WIDE_ANAMORPHIC;
    const char *chart_path = DEFAULT_CHART;
    const char *inst_path = DEFAULT_INST;
    const char *voices_path = DEFAULT_VOICES;
    boolean audio_ok;
    boolean disc_ok;
    ChartResult game_result = CHART_ERR_IO;

    printf("\nFNF PS2 native port\n");
    printf("logical canvas: 640x360\n");
    printf("SELECT: toggle 16:9 / 4:3 letterbox\n");
    printf("notes: d-pad OR square/cross/triangle/circle\n");

    SifInitRpc(0);
    Pad_Init();
    gs = init_video();
    Timer_Init();

    Animatable_Init(&g_boot_anim, g_boot_anims);
    Animatable_SetAnim(&g_boot_anim, 0);

    audio_ok = Audio_Init();
    disc_ok = Disc_Init();
    printf("[PS2] audio=%s disc=%s\n", audio_ok ? "ok" : "failed", disc_ok ? "ok" : "failed");

    /* ps2client may supply host: paths for fast emulator/hardware iteration. */
    if (argc >= 3) {
        chart_path = argv[1];
        inst_path = argv[2];
        voices_path = (argc >= 4) ? argv[3] : NULL;
    }

    if (audio_ok && (argc >= 3 || disc_ok)) {
        game_result = Gameplay_Load(
            &g_gameplay,
            chart_path,
            inst_path,
            voices_path,
            false,
            false,
            FIXED_DEC(1, 1));
        if (game_result == CHART_OK) {
            g_gameplay_loaded = true;
            printf("[PS2] gameplay loaded: %u notes, %u sections\n",
                (unsigned)g_gameplay.chart.view.note_count,
                (unsigned)g_gameplay.chart.view.section_count);
        } else {
            printf("[PS2] gameplay load failed: %s\n", Chart_ResultString(game_result));
        }
    }

    for (;;) {
        Pad_Update();
        Timer_Tick();
        Animatable_Animate(&g_boot_anim, &g_boot_anim_frame, boot_set_frame);

        if (pad_state.press & PAD_SELECT) {
            aspect = (aspect == ASPECT_WIDE_ANAMORPHIC)
                ? ASPECT_LETTERBOX_4_3
                : ASPECT_WIDE_ANAMORPHIC;
            printf("[PS2] aspect = %s\n",
                aspect == ASPECT_WIDE_ANAMORPHIC ? "16:9 anamorphic" : "4:3 letterbox");
        }

        if (g_gameplay_loaded) {
            Gameplay_Tick(&g_gameplay, &pad_state);
            render_gameplay(gs, aspect, &g_gameplay);
        } else {
            render_boot_test(gs, aspect);
        }
    }

    return 0;
}
