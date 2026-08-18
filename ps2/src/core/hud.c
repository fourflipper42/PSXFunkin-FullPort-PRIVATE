#include "hud.h"

#include <stdio.h>
#include <string.h>

#define HUD_BAR_X 170.0f
#define HUD_BAR_Y 330.0f
#define HUD_BAR_W 300.0f
#define HUD_BAR_H 10.0f

static float g_x_scale = 1.0f;
static float g_y_scale = 1.0f;
static float g_x_offset = 0.0f;
static float g_y_offset = 0.0f;

static float hx(float x) { return g_x_offset + x * g_x_scale; }
static float hy(float y) { return g_y_offset + y * g_y_scale; }

static void rect(
    GSGLOBAL *gs,
    float x1,
    float y1,
    float x2,
    float y2,
    int z,
    u64 color)
{
    gsKit_prim_sprite(gs, hx(x1), hy(y1), hx(x2), hy(y2), z, color);
}

static u8 alpha_from_percent(u8 percent)
{
    if (percent > 100) percent = 100;
    return (u8)(((u32)percent * 128u + 50u) / 100u);
}

static boolean load_optional_texture(GSGLOBAL *gs, TextureAsset *texture, const char *path)
{
    if (gs == NULL || texture == NULL || path == NULL)
        return false;
    return TextureAsset_Load(gs, texture, path, true);
}

void Hud_SetDrawTransform(
    float x_scale,
    float y_scale,
    float x_offset,
    float y_offset)
{
    g_x_scale = x_scale;
    g_y_scale = y_scale;
    g_x_offset = x_offset;
    g_y_offset = y_offset;
}

void Hud_Init(HudRuntime *hud)
{
    if (hud != NULL)
        memset(hud, 0, sizeof(*hud));
}

void Hud_SetGameplayMode(
    HudRuntime *hud,
    boolean hidden,
    boolean suppress_scoring_ui)
{
    if (hud == NULL)
        return;
    hud->hidden = hidden;
    hud->suppress_scoring_ui = suppress_scoring_ui;
}

boolean Hud_LoadSong(
    GSGLOBAL *gs,
    HudRuntime *hud,
    const char *player_base,
    const char *opponent_base)
{
    if (gs == NULL || hud == NULL)
        return false;

    Hud_ForgetSong(hud);
    hud->player_icon_loaded = HealthIcon_Load(gs, &hud->player_icon, player_base);
    hud->opponent_icon_loaded = HealthIcon_Load(gs, &hud->opponent_icon, opponent_base);

    hud->fc_loaded = load_optional_texture(
        gs, &hud->fc_texture, "\\GAME\\MODHUD\\FC.FPTX;1");
    hud->fc_death_loaded = load_optional_texture(
        gs, &hud->fc_death_texture, "\\GAME\\MODHUD\\FC1.FPTX;1");
    return hud->player_icon_loaded || hud->opponent_icon_loaded;
}

void Hud_ForgetSong(HudRuntime *hud)
{
    if (hud == NULL)
        return;
    if (hud->player_icon_loaded)
        HealthIcon_Forget(&hud->player_icon);
    if (hud->opponent_icon_loaded)
        HealthIcon_Forget(&hud->opponent_icon);
    if (hud->fc_loaded)
        TextureAsset_Forget(&hud->fc_texture);
    if (hud->fc_death_loaded)
        TextureAsset_Forget(&hud->fc_death_texture);
    memset(hud, 0, sizeof(*hud));
}

void Hud_OnBeat(
    HudRuntime *hud,
    s32 beat,
    const FunkinSaveData *save)
{
    HealthIconBounceStyle style;

    if (hud == NULL || save == NULL)
        return;
    style = save->hud_icon_bounce_style == 1
        ? HEALTH_ICON_BOUNCE_CLASSIC
        : HEALTH_ICON_BOUNCE_REWORKED;
    if (hud->player_icon_loaded)
        HealthIcon_OnBeat(&hud->player_icon, beat, true, style);
    if (hud->opponent_icon_loaded)
        HealthIcon_OnBeat(&hud->opponent_icon, beat, false, style);
}

void Hud_Tick(
    HudRuntime *hud,
    GameplayState *game,
    ComboSystem *combo,
    const FunkinSaveData *save,
    fixed_t elapsed)
{
    HealthIconBounceStyle style;
    u32 value;
    boolean play_sound;

    if (hud == NULL || game == NULL || save == NULL)
        return;
    style = save->hud_icon_bounce_style == 1
        ? HEALTH_ICON_BOUNCE_CLASSIC
        : HEALTH_ICON_BOUNCE_REWORKED;

    if (hud->player_icon_loaded)
        HealthIcon_Tick(&hud->player_icon, elapsed, game->rhythm.health, true, style);
    if (hud->opponent_icon_loaded)
        HealthIcon_Tick(&hud->opponent_icon, elapsed, game->rhythm.health, false, style);

    if (combo != NULL && ComboSystem_TakePopup(combo, &value)) {
        hud->popup_combo = value;
        hud->popup_timer = FIXED_DEC(4, 5);
    }
    if (combo != NULL && ComboSystem_TakeSwoosh(combo, &value, &play_sound)) {
        hud->swoosh_combo = value;
        hud->swoosh_timer = FIXED_DEC(3, 4);
        hud->swoosh_sound_pending = play_sound;
    }

    if (hud->popup_timer > 0) {
        hud->popup_timer -= elapsed;
        if (hud->popup_timer < 0) hud->popup_timer = 0;
    }
    if (hud->swoosh_timer > 0) {
        hud->swoosh_timer -= elapsed;
        if (hud->swoosh_timer < 0) hud->swoosh_timer = 0;
    }
}

static void draw_fc(
    GSGLOBAL *gs,
    const HudRuntime *hud,
    const GameplayState *game,
    const FunkinSaveData *save,
    GSFONTM *font)
{
    const TextureAsset *asset = NULL;
    float health_ratio;
    float split_x;
    float scale;
    float w;
    float h;
    float y;
    u8 alpha;
    u64 color;

    if (!(save->settings_flags & SAVE_FLAG_HUD_FC_INDICATOR))
        return;
    health_ratio = (float)game->rhythm.health / 20000.0f;
    if (health_ratio < 0.0f) health_ratio = 0.0f;
    if (health_ratio > 1.0f) health_ratio = 1.0f;
    split_x = HUD_BAR_X + HUD_BAR_W * health_ratio;
    alpha = alpha_from_percent(save->hud_fc_opacity);
    color = GS_SETREG_RGBAQ(0x80, 0x80, 0x80, alpha, 0);

    if (save->hud_fc_style == 1 && hud->fc_death_loaded)
        asset = &hud->fc_death_texture;
    else if (hud->fc_loaded)
        asset = &hud->fc_texture;

    if (asset != NULL) {
        scale = 0.20f * ((float)save->hud_fc_size_tenths / 10.0f);
        w = (float)asset->texture.Width * scale;
        h = (float)asset->texture.Height * scale;
        y = HUD_BAR_Y + (HUD_BAR_H - h) * 0.5f + 0.5f;
        TextureAsset_Draw(
            gs, asset,
            split_x - w * 0.5f, y,
            split_x + w * 0.5f, y + h,
            0.0f, 0.0f,
            (float)asset->texture.Width, (float)asset->texture.Height,
            13, color);
    } else if (font != NULL) {
        gsKit_fontm_print_scaled(gs, font, hx(split_x - 8.0f), hy(HUD_BAR_Y - 4.0f),
            13, 0.28f, color, "FC");
    }
}

static float approximate_text_width(const char *text, float scale)
{
    return text != NULL ? (float)strlen(text) * 13.0f * scale : 0.0f;
}

static void draw_score(
    GSGLOBAL *gs,
    const GameplayState *game,
    const FunkinSaveData *save,
    GSFONTM *font)
{
    char text[64];
    float scale;
    float x;
    float y;
    float width;
    u64 white = GS_SETREG_RGBAQ(0x80, 0x80, 0x80, 0x80, 0x00);

    if (font == NULL || !(save->settings_flags & SAVE_FLAG_HUD_SCORE_VISIBLE))
        return;
    snprintf(text, sizeof(text), "Score: %d", (int)game->rhythm.score);
    scale = (float)save->hud_score_size / 40.0f;
    if (scale < 0.20f) scale = 0.20f;
    if (scale > 1.8f) scale = 1.8f;
    width = approximate_text_width(text, scale);

    switch (save->hud_score_position) {
        case 1:
            x = 626.0f - width;
            y = 14.0f;
            break;
        case 2:
            x = 14.0f;
            y = 14.0f;
            break;
        case 3:
            x = 14.0f;
            y = 336.0f;
            break;
        case 4:
            x = 626.0f - width;
            y = 336.0f;
            break;
        default:
            x = HUD_BAR_X + HUD_BAR_W - 95.0f;
            y = HUD_BAR_Y + 15.0f;
            break;
    }
    gsKit_fontm_print_scaled(gs, font, hx(x), hy(y), 14, scale, white, text);
}

static void draw_combo_effects(
    GSGLOBAL *gs,
    const HudRuntime *hud,
    const FunkinSaveData *save,
    GSFONTM *font)
{
    char text[48];
    u64 white = GS_SETREG_RGBAQ(0x80, 0x80, 0x80, 0x80, 0x00);
    float x;

    if (font == NULL)
        return;
    if (hud->popup_timer > 0 && (save->settings_flags & SAVE_FLAG_COMBO_POPUPS)) {
        snprintf(text, sizeof(text), "COMBO %u", (unsigned)hud->popup_combo);
        x = save->hud_combo_style == 1 ? 330.0f : 238.0f;
        gsKit_fontm_print_scaled(gs, font, hx(x), hy(202.0f), 15, 0.54f, white, text);
    }
    if (hud->swoosh_timer > 0 && (save->settings_flags & SAVE_FLAG_COMBO_SWOOSH)) {
        snprintf(text, sizeof(text), "%u!", (unsigned)hud->swoosh_combo);
        gsKit_fontm_print_scaled(gs, font, hx(282.0f), hy(172.0f), 16, 0.72f, white, text);
    }
}

void Hud_Draw(
    GSGLOBAL *gs,
    const HudRuntime *hud,
    const GameplayState *game,
    const FunkinSaveData *save,
    GSFONTM *font)
{
    float health_ratio;
    u8 bar_alpha;
    u8 icon_opacity;
    u64 background;
    u64 opponent;
    u64 player;
    HealthIconPositionMode position;

    if (gs == NULL || hud == NULL || game == NULL || save == NULL || hud->hidden)
        return;

    health_ratio = (float)game->rhythm.health / 20000.0f;
    if (health_ratio < 0.0f) health_ratio = 0.0f;
    if (health_ratio > 1.0f) health_ratio = 1.0f;
    bar_alpha = alpha_from_percent(save->hud_health_bar_opacity);
    icon_opacity = save->hud_icons_opacity > 100 ? 100 : save->hud_icons_opacity;
    background = GS_SETREG_RGBAQ(0x20, 0x20, 0x20, bar_alpha, 0);
    opponent = GS_SETREG_RGBAQ(0xd8, 0x38, 0x48, bar_alpha, 0);
    player = GS_SETREG_RGBAQ(0x45, 0xd8, 0x78, bar_alpha, 0);

    rect(gs, HUD_BAR_X - 2.0f, HUD_BAR_Y - 2.0f,
        HUD_BAR_X + HUD_BAR_W + 2.0f, HUD_BAR_Y + HUD_BAR_H + 2.0f,
        10, background);
    rect(gs, HUD_BAR_X, HUD_BAR_Y,
        HUD_BAR_X + HUD_BAR_W, HUD_BAR_Y + HUD_BAR_H,
        11, opponent);
    rect(gs, HUD_BAR_X, HUD_BAR_Y,
        HUD_BAR_X + HUD_BAR_W * health_ratio, HUD_BAR_Y + HUD_BAR_H,
        12, player);

    position = save->hud_icons_position > 2
        ? HEALTH_ICON_POSITION_DEFAULT
        : (HealthIconPositionMode)save->hud_icons_position;
    if (hud->player_icon_loaded)
        HealthIcon_Draw(gs, &hud->player_icon,
            HUD_BAR_X, HUD_BAR_Y, HUD_BAR_W, HUD_BAR_H,
            game->rhythm.health, true, position,
            (float)icon_opacity / 100.0f, 13);
    if (hud->opponent_icon_loaded)
        HealthIcon_Draw(gs, &hud->opponent_icon,
            HUD_BAR_X, HUD_BAR_Y, HUD_BAR_W, HUD_BAR_H,
            game->rhythm.health, false, position,
            (float)icon_opacity / 100.0f, 13);

    if (!hud->suppress_scoring_ui) {
        draw_fc(gs, hud, game, save, font);
        draw_score(gs, game, save, font);
        draw_combo_effects(gs, hud, save, font);
    }
}
