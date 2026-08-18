#ifndef FNF_PS2_HUD_H
#define FNF_PS2_HUD_H

#include "combo_system.h"
#include "gameplay.h"
#include "health_icon.h"
#include "save_data.h"
#include "texture_asset.h"
#include <gsToolkit.h>

typedef struct HudRuntime {
    HealthIcon player_icon;
    HealthIcon opponent_icon;
    TextureAsset fc_texture;
    TextureAsset fc_death_texture;
    boolean player_icon_loaded;
    boolean opponent_icon_loaded;
    boolean fc_loaded;
    boolean fc_death_loaded;
    boolean hidden;
    boolean suppress_scoring_ui;
    u32 popup_combo;
    u32 swoosh_combo;
    fixed_t popup_timer;
    fixed_t swoosh_timer;
    boolean swoosh_sound_pending;
} HudRuntime;

void Hud_SetDrawTransform(
    float x_scale,
    float y_scale,
    float x_offset,
    float y_offset);
void Hud_Init(HudRuntime *hud);
void Hud_SetGameplayMode(
    HudRuntime *hud,
    boolean hidden,
    boolean suppress_scoring_ui);
boolean Hud_LoadSong(
    GSGLOBAL *gs,
    HudRuntime *hud,
    const char *player_base,
    const char *opponent_base);
void Hud_ForgetSong(HudRuntime *hud);
void Hud_OnBeat(
    HudRuntime *hud,
    s32 beat,
    const FunkinSaveData *save);
void Hud_Tick(
    HudRuntime *hud,
    GameplayState *game,
    ComboSystem *combo,
    const FunkinSaveData *save,
    fixed_t elapsed);
void Hud_Draw(
    GSGLOBAL *gs,
    const HudRuntime *hud,
    const GameplayState *game,
    const FunkinSaveData *save,
    GSFONTM *font);

#endif
