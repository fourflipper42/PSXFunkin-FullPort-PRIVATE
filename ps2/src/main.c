#include <stdio.h>
#include <string.h>
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
#include "core/song_descriptor.h"
#include "core/texture_asset.h"
#include "core/note_style.h"
#include "core/note_lane_renderer.h"
#include "core/stage.h"
#include "core/character.h"

#define LOGICAL_W 640.0f
#define LOGICAL_H 360.0f
#define NTSC_W    640.0f
#define NTSC_H    448.0f

#define DEFAULT_DESCRIPTOR "\\GAME\\SONG\\TUTORIAL\\DEFAULT\\NORMAL.FSON;1"
#define STAGE_Z_MIN        ((s32)-0x7fffffff)
#define STAGE_Z_MAX        ((s32)0x7fffffff)

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

typedef struct CharacterLayer {
    Character *character;
    const StageCharacterSlot *slot;
} CharacterLayer;

static u8 g_boot_anim_frame = 0;
static const u8 g_boot_anim_script[] = {
    0, 1, 2, 3, 2, 1, ASCR_REPEAT
};
static const Animation g_boot_anims[] = {
    {2, g_boot_anim_script}
};
static Animatable g_boot_anim;
static GameplayState g_gameplay;
static SongDescriptor g_song_descriptor;
static SongAssetPaths g_song_paths;
static NoteStyle g_note_style;
static Stage g_stage;
static StageCamera g_stage_camera;
static Character g_player;
static Character g_opponent;
static Character g_girlfriend;
static boolean g_gameplay_loaded;
static boolean g_descriptor_loaded;
static boolean g_note_style_loaded;
static boolean g_stage_loaded;
static boolean g_player_loaded;
static boolean g_opponent_loaded;
static boolean g_girlfriend_loaded;
static int g_camera_focus;

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
        const float content_h = LOGICAL_H * t.x_scale;
        t.y_scale = t.x_scale;
        t.y_offset = (NTSC_H - content_h) * 0.5f;
    } else {
        t.y_scale = NTSC_H / LOGICAL_H;
        t.y_offset = 0.0f;
    }

    return t;
}

static void apply_video_transform(AspectMode mode)
{
    VideoTransform t = video_transform(mode);
    TextureAsset_SetDrawTransform(t.x_scale, t.y_scale, t.x_offset, t.y_offset);
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
    TextureAsset_EndFrame(gs);
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

static u64 character_color(const StageCharacterSlot *slot)
{
    float alpha = slot != NULL ? slot->alpha : 1.0f;
    u8 a;

    if (alpha < 0.0f)
        alpha = 0.0f;
    if (alpha > 1.0f)
        alpha = 1.0f;
    a = (u8)(alpha * 128.0f + 0.5f);
    return GS_SETREG_RGBAQ(0x80, 0x80, 0x80, a, 0);
}

static void draw_character_layer(
    GSGLOBAL *gs,
    const CharacterLayer *layer,
    const StageCamera *camera)
{
    float zoom;
    float world_scale;
    float x;
    float y;

    if (layer == NULL || layer->character == NULL || layer->slot == NULL ||
        !layer->character->loaded)
        return;

    zoom = camera != NULL ? camera->zoom : 1.0f;
    if (zoom <= 0.0f)
        zoom = 1.0f;
    world_scale = 0.5f * zoom;
    x = (layer->slot->x -
        ((camera != NULL ? camera->scroll_x : 0.0f) * layer->slot->scroll_x)) * world_scale;
    y = (layer->slot->y -
        ((camera != NULL ? camera->scroll_y : 0.0f) * layer->slot->scroll_y)) * world_scale;

    Character_Draw(
        gs,
        layer->character,
        x,
        y,
        layer->slot->scale * world_scale,
        2,
        character_color(layer->slot));
}

static void render_world(GSGLOBAL *gs)
{
    CharacterLayer layers[3];
    int count = 0;
    int i;
    int j;
    s32 z_cursor = STAGE_Z_MIN;

    if (!g_stage_loaded)
        return;

    if (g_opponent_loaded) {
        layers[count].character = &g_opponent;
        layers[count].slot = Stage_OpponentSlot(&g_stage);
        ++count;
    }
    if (g_girlfriend_loaded) {
        layers[count].character = &g_girlfriend;
        layers[count].slot = Stage_GirlfriendSlot(&g_stage);
        ++count;
    }
    if (g_player_loaded) {
        layers[count].character = &g_player;
        layers[count].slot = Stage_PlayerSlot(&g_stage);
        ++count;
    }

    for (i = 1; i < count; ++i) {
        CharacterLayer key = layers[i];
        j = i - 1;
        while (j >= 0 && layers[j].slot->z_index > key.slot->z_index) {
            layers[j + 1] = layers[j];
            --j;
        }
        layers[j + 1] = key;
    }

    for (i = 0; i < count; ++i) {
        s32 z = layers[i].slot->z_index;
        Stage_DrawRange(gs, &g_stage, &g_stage_camera, z_cursor, z);
        draw_character_layer(gs, &layers[i], &g_stage_camera);
        z_cursor = z;
    }
    Stage_DrawRange(gs, &g_stage, &g_stage_camera, z_cursor, STAGE_Z_MAX);
}

static void render_fallback_lanes(
    GSGLOBAL *gs,
    const VideoTransform *t,
    GameplayState *game)
{
    const u64 black = GS_SETREG_RGBAQ(0x00, 0x00, 0x00, 0x80, 0x00);
    const u64 receptor = GS_SETREG_RGBAQ(0xe8, 0xe8, 0xe8, 0x80, 0x00);
    const u64 mine = GS_SETREG_RGBAQ(0x10, 0x10, 0x10, 0x80, 0x00);
    const float receptor_y = 54.0f;
    ChartView *chart = &game->chart.view;
    size_t i;
    int lane;

    for (lane = 0; lane < 4; ++lane) {
        float ox = lane_x(true, (u8)lane);
        float px = lane_x(false, (u8)lane);
        draw_logical_rect(gs, t, ox, receptor_y, ox + 30.0f, receptor_y + 30.0f, 4, receptor);
        draw_logical_rect(gs, t, px, receptor_y, px + 30.0f, receptor_y + 30.0f, 4, receptor);
        draw_logical_rect(gs, t, ox + 3.0f, receptor_y + 3.0f, ox + 27.0f, receptor_y + 27.0f, 5, black);
        draw_logical_rect(gs, t, px + 3.0f, receptor_y + 3.0f, px + 27.0f, receptor_y + 27.0f, 5, black);
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
        draw_logical_rect(gs, t, x, y, x + w, y + h, 3, color);
    }
}

static void render_gameplay(GSGLOBAL *gs, AspectMode aspect, GameplayState *game)
{
    const u64 black = GS_SETREG_RGBAQ(0x00, 0x00, 0x00, 0x80, 0x00);
    const u64 fallback_bg = GS_SETREG_RGBAQ(0x1b, 0x16, 0x25, 0x80, 0x00);
    const u64 health_bg = GS_SETREG_RGBAQ(0x38, 0x38, 0x38, 0x80, 0x00);
    const u64 health_fg = GS_SETREG_RGBAQ(0xe8, 0xe8, 0xe8, 0x80, 0x00);
    VideoTransform t = video_transform(aspect);
    float health_ratio;

    gsKit_clear(gs, black);
    if (g_stage_loaded)
        render_world(gs);
    else
        draw_logical_rect(gs, &t, 0.0f, 0.0f, 640.0f, 360.0f, 1, fallback_bg);

    if (g_note_style_loaded)
        NoteLaneRenderer_Draw(gs, &g_note_style, game, &pad_state);
    else
        render_fallback_lanes(gs, &t, game);

    health_ratio = (float)game->rhythm.health / 20000.0f;
    if (health_ratio < 0.0f)
        health_ratio = 0.0f;
    if (health_ratio > 1.0f)
        health_ratio = 1.0f;
    draw_logical_rect(gs, &t, 170.0f, 330.0f, 470.0f, 340.0f, 8, health_bg);
    draw_logical_rect(gs, &t, 170.0f, 330.0f, 170.0f + 300.0f * health_ratio, 340.0f, 9, health_fg);

    gsKit_queue_exec(gs);
    gsKit_sync_flip(gs);
    TextureAsset_EndFrame(gs);
}

static boolean load_character_from_base(
    GSGLOBAL *gs,
    Character *character,
    const char *base)
{
    char config[320];
    char texture[320];
    char frames[320];

    if (base == NULL || base[0] == '\0')
        return false;

    SongDescriptor_CharacterFile(config, sizeof(config), base, "CHAR.FCHR");
    SongDescriptor_CharacterFile(texture, sizeof(texture), base, "ATLAS.FPTX");
    SongDescriptor_CharacterFile(frames, sizeof(frames), base, "ATLAS.FATL");
    if (config[0] == '\0' || texture[0] == '\0' || frames[0] == '\0')
        return false;

    if (!Character_Load(gs, character, config, texture, frames)) {
        printf("[PS2] character load failed: %s\n", base);
        return false;
    }
    return true;
}

static const StageCharacterSlot *focused_slot(void)
{
    if (!g_stage_loaded)
        return NULL;

    switch (g_camera_focus) {
        case 1:
            return Stage_OpponentSlot(&g_stage);
        case 2:
            return Stage_GirlfriendSlot(&g_stage);
        default:
            return Stage_PlayerSlot(&g_stage);
    }
}

static void snap_camera_to_focus(void)
{
    const StageCharacterSlot *slot = focused_slot();
    float zoom;

    if (slot == NULL)
        return;
    zoom = g_stage_camera.zoom;
    if (zoom <= 0.0f)
        zoom = 1.0f;

    g_stage_camera.scroll_x = slot->x + slot->camera_x - (LOGICAL_W / (0.5f * zoom));
    g_stage_camera.scroll_y = slot->y + slot->camera_y - (LOGICAL_H / (0.5f * zoom));
}

static void tick_camera(void)
{
    const StageCharacterSlot *slot = focused_slot();
    float zoom;
    float target_x;
    float target_y;
    float dt;
    float alpha;

    if (slot == NULL)
        return;

    zoom = g_stage_camera.zoom;
    if (zoom <= 0.0f)
        zoom = 1.0f;
    target_x = slot->x + slot->camera_x - (LOGICAL_W / (0.5f * zoom));
    target_y = slot->y + slot->camera_y - (LOGICAL_H / (0.5f * zoom));

    dt = (float)timer_dt / (float)FIXED_UNIT;
    alpha = dt * 8.0f;
    if (alpha < 0.0f)
        alpha = 0.0f;
    if (alpha > 1.0f)
        alpha = 1.0f;

    g_stage_camera.scroll_x += (target_x - g_stage_camera.scroll_x) * alpha;
    g_stage_camera.scroll_y += (target_y - g_stage_camera.scroll_y) * alpha;
}

static void load_presentation_assets(GSGLOBAL *gs)
{
    if (!g_descriptor_loaded)
        return;

    g_note_style_loaded = NoteStyle_Load(gs, &g_note_style, g_song_paths.note_style_base);
    NoteLaneRenderer_Reset();
    printf("[PS2] note style %s: %s\n",
        g_song_descriptor.note_style,
        g_note_style_loaded ? "ok" : "missing");

    if (g_song_paths.stage_base[0] != '\0') {
        g_stage_loaded = Stage_Load(gs, &g_stage, g_song_paths.stage_base);
        if (g_stage_loaded) {
            g_stage_camera.scroll_x = 0.0f;
            g_stage_camera.scroll_y = 0.0f;
            g_stage_camera.zoom = Stage_CameraZoom(&g_stage);
            if (g_stage_camera.zoom <= 0.0f)
                g_stage_camera.zoom = 1.0f;
            printf("[PS2] stage loaded: %s (%u props, zoom %.3f)\n",
                g_song_descriptor.stage,
                (unsigned)g_stage.prop_count,
                g_stage_camera.zoom);
        } else {
            printf("[PS2] stage load failed: %s\n", g_song_paths.stage_base);
        }
    }

    g_player_loaded = load_character_from_base(gs, &g_player, g_song_paths.player_base);
    g_opponent_loaded = load_character_from_base(gs, &g_opponent, g_song_paths.opponent_base);
    g_girlfriend_loaded = load_character_from_base(gs, &g_girlfriend, g_song_paths.girlfriend_base);

    if (g_stage_loaded)
        snap_camera_to_focus();

    printf("[PS2] presentation: bf=%s dad=%s gf=%s\n",
        g_player_loaded ? "ok" : "missing",
        g_opponent_loaded ? "ok" : "missing",
        g_girlfriend_loaded ? "ok" : "missing");
}

static void play_lane_animation(Character *character, u8 mask)
{
    static const char *names[4] = {
        "singLEFT", "singDOWN", "singUP", "singRIGHT"
    };
    int lane;

    if (character == NULL || !character->loaded || mask == 0)
        return;

    for (lane = 0; lane < 4; ++lane) {
        if (mask & (1u << lane))
            Character_Play(character, names[lane], true);
    }
}

static boolean character_is_singing(const Character *character)
{
    const char *name = Character_CurrentAnimationName(character);
    return name != NULL && strncmp(name, "sing", 4) == 0;
}

static void dance_character_on_beat(Character *character, s32 beat)
{
    s32 cadence;

    if (character == NULL || !character->loaded)
        return;
    cadence = (s32)(character->dance_every + 0.5f);
    if (cadence < 1)
        cadence = 1;
    if ((beat % cadence) != 0)
        return;
    if (!character_is_singing(character) || Character_AnimationFinished(character))
        Character_Dance(character, true);
}

static void consume_gameplay_events(void)
{
    if (g_gameplay.events.camera_focus_changed) {
        g_camera_focus = g_gameplay.events.camera_focus;
        printf("[PS2] FocusCamera -> %s\n",
            g_camera_focus == 0 ? "player" :
            (g_camera_focus == 1 ? "opponent" : "girlfriend"));
    }

    if (g_gameplay.events.song_event_fired &&
        g_gameplay.events.last_song_event_kind == SONG_EVENT_GENERIC &&
        g_gameplay.events.last_song_event_name != NULL &&
        g_gameplay.events.last_song_event_value != NULL) {
        printf("[PS2] event %s value=%s\n",
            g_gameplay.events.last_song_event_name,
            g_gameplay.events.last_song_event_value);
    }
}

static void tick_presentation(void)
{
    if (g_gameplay_loaded) {
        consume_gameplay_events();
        play_lane_animation(&g_player, g_gameplay.events.player_hit_mask);
        play_lane_animation(&g_opponent, g_gameplay.events.opponent_hit_mask);

        if (g_gameplay.events.just_step && g_gameplay.song_step >= 0 &&
            (g_gameplay.song_step & 3) == 0) {
            s32 beat = g_gameplay.song_step / 4;
            if (g_stage_loaded)
                Stage_Beat(&g_stage, beat);
            dance_character_on_beat(&g_player, beat);
            dance_character_on_beat(&g_opponent, beat);
            dance_character_on_beat(&g_girlfriend, beat);
        }
    }

    tick_camera();
    if (g_stage_loaded)
        Stage_Tick(&g_stage);
    if (g_player_loaded)
        Character_Tick(&g_player);
    if (g_opponent_loaded)
        Character_Tick(&g_opponent);
    if (g_girlfriend_loaded)
        Character_Tick(&g_girlfriend);
}

static boolean load_descriptor_song(GSGLOBAL *gs, const char *descriptor_path)
{
    ChartResult result;

    if (!SongDescriptor_Load(&g_song_descriptor, descriptor_path)) {
        printf("[PS2] song descriptor load failed: %s\n", descriptor_path);
        return false;
    }
    g_descriptor_loaded = true;

    if (!SongDescriptor_BuildDiscPaths(&g_song_descriptor, &g_song_paths)) {
        printf("[PS2] descriptor path build failed\n");
        SongDescriptor_Free(&g_song_descriptor);
        g_descriptor_loaded = false;
        return false;
    }

    printf("[PS2] song: %s / %s / %s\n",
        g_song_descriptor.display_name,
        g_song_descriptor.variation,
        g_song_descriptor.difficulty);
    printf("[PS2] stage=%s notes=%s player=%s opponent=%s gf=%s\n",
        g_song_descriptor.stage,
        g_song_descriptor.note_style,
        g_song_descriptor.player,
        g_song_descriptor.opponent,
        g_song_descriptor.girlfriend);

    result = Gameplay_Load(
        &g_gameplay,
        g_song_paths.chart,
        g_song_paths.inst,
        g_song_paths.voices,
        false,
        false,
        g_song_descriptor.scroll_speed);
    if (result != CHART_OK) {
        printf("[PS2] gameplay load failed: %s\n", Chart_ResultString(result));
        return false;
    }

    g_camera_focus = 0;
    g_gameplay_loaded = true;
    load_presentation_assets(gs);
    printf("[PS2] gameplay loaded: %u notes, %u sections, %u events\n",
        (unsigned)g_gameplay.chart.view.note_count,
        (unsigned)g_gameplay.chart.view.section_count,
        g_gameplay.song_events.loaded ? (unsigned)g_gameplay.song_events.count : 0u);
    return true;
}

int main(int argc, char **argv)
{
    GSGLOBAL *gs;
    AspectMode aspect = ASPECT_WIDE_ANAMORPHIC;
    boolean audio_ok;
    boolean disc_ok;

    printf("\nFNF PS2 native port\n");
    printf("logical canvas: 640x360\n");
    printf("SELECT: toggle 16:9 / 4:3 letterbox\n");
    printf("notes: d-pad OR square/cross/triangle/circle\n");

    SifInitRpc(0);
    Pad_Init();
    gs = init_video();
    TextureAsset_InitStreaming(gs);
    apply_video_transform(aspect);
    Timer_Init();
    NoteLaneRenderer_Reset();

    Animatable_Init(&g_boot_anim, g_boot_anims);
    Animatable_SetAnim(&g_boot_anim, 0);

    audio_ok = Audio_Init();
    disc_ok = Disc_Init();
    printf("[PS2] audio=%s disc=%s\n", audio_ok ? "ok" : "failed", disc_ok ? "ok" : "failed");

    if (audio_ok) {
        if (argc >= 3) {
            ChartResult result = Gameplay_Load(
                &g_gameplay,
                argv[1],
                argv[2],
                argc >= 4 ? argv[3] : NULL,
                false,
                false,
                FIXED_DEC(1, 1));
            if (result == CHART_OK) {
                g_gameplay_loaded = true;
                printf("[PS2] direct gameplay loaded: %u notes\n",
                    (unsigned)g_gameplay.chart.view.note_count);
            } else {
                printf("[PS2] direct gameplay load failed: %s\n", Chart_ResultString(result));
            }
        } else if (disc_ok) {
            load_descriptor_song(gs, DEFAULT_DESCRIPTOR);
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
            apply_video_transform(aspect);
            printf("[PS2] aspect = %s\n",
                aspect == ASPECT_WIDE_ANAMORPHIC ? "16:9 anamorphic" : "4:3 letterbox");
        }

        if (g_gameplay_loaded) {
            Gameplay_Tick(&g_gameplay, &pad_state);
            NoteLaneRenderer_Tick(&g_gameplay, &pad_state);
            tick_presentation();
            render_gameplay(gs, aspect, &g_gameplay);
        } else {
            render_boot_test(gs, aspect);
        }
    }

    return 0;
}
