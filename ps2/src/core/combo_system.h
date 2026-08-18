#ifndef FNF_PS2_COMBO_SYSTEM_H
#define FNF_PS2_COMBO_SYSTEM_H

#include "gameplay.h"

typedef enum ComboSwooshPosition {
    COMBO_SWOOSH_LEFT = 0,
    COMBO_SWOOSH_DEFAULT,
    COMBO_SWOOSH_RIGHT
} ComboSwooshPosition;

typedef struct ComboSystem {
    boolean popups_enabled;
    boolean swoosh_enabled;
    boolean sound_enabled;
    boolean reverse_numbers;
    boolean popup_pending;
    boolean swoosh_pending;
    u16 swoosh_threshold;
    ComboSwooshPosition position;
    u32 grouped_combo;
    u32 popup_combo;
    u32 swoosh_combo;
    s32 swoosh_due_step;
} ComboSystem;

void ComboSystem_Init(ComboSystem *combo);
void ComboSystem_Configure(
    ComboSystem *combo,
    boolean popups,
    boolean swoosh,
    boolean sound,
    boolean reverse_numbers,
    u16 threshold,
    ComboSwooshPosition position);
void ComboSystem_ResetSong(ComboSystem *combo);
void ComboSystem_OnGameplayFrame(ComboSystem *combo, const GameplayState *game);
boolean ComboSystem_TakePopup(ComboSystem *combo, u32 *value);
boolean ComboSystem_TakeSwoosh(ComboSystem *combo, u32 *value, boolean *play_sound);

#endif
