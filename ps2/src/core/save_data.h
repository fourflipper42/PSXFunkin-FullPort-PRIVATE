#ifndef FNF_PS2_SAVE_DATA_H
#define FNF_PS2_SAVE_DATA_H

#include "progression.h"

#define FNF_SAVE_VERSION 1
#define FNF_SAVE_PIN_SLOTS 64
#define FNF_SAVE_BOX_SLOTS 8
#define FNF_SAVE_PREVIOUS_SONGS 5
#define FNF_SAVE_DAILY_SONGS 3
#define FNF_SAVE_GAMMOD_SLOTS 32

#define SAVE_FLAG_CAMERA_MOVEMENT       (1u << 0)
#define SAVE_FLAG_CAMERA_ONLY_PLAYER    (1u << 1)
#define SAVE_FLAG_COMBO_POPUPS          (1u << 2)
#define SAVE_FLAG_COMBO_SWOOSH          (1u << 3)
#define SAVE_FLAG_COMBO_SOUND           (1u << 4)
#define SAVE_FLAG_ENDLESS_DEFAULT       (1u << 5)
#define SAVE_FLAG_HUD_FC_INDICATOR      (1u << 6)
#define SAVE_FLAG_HUD_ICON_BOUNCE       (1u << 7)
#define SAVE_FLAG_HUD_SCORE_BOUNCE      (1u << 8)
#define SAVE_FLAG_PIN_MODIFIER_MULT     (1u << 9)
#define SAVE_FLAG_COMBO_REVERSE_NUMBERS (1u << 10)

typedef struct FunkinSaveData {
    char magic[4];
    u16 version;
    u16 size;
    u32 checksum;
    u32 reserved_header;

    u64 completed_story_levels;
    u32 settings_flags;
    u32 funkbucks;
    u32 funkbucks_lifetime;

    u8 health_drain_level;
    u8 camera_movement_intensity;
    u8 combo_swoosh_threshold;
    u8 hud_layout;

    u16 pin_counts[FNF_SAVE_PIN_SLOTS];
    u16 opened_box_counts[FNF_SAVE_BOX_SLOTS];
    u32 previous_song_hashes[FNF_SAVE_PREVIOUS_SONGS];
    u32 daily_song_hashes[FNF_SAVE_DAILY_SONGS];
    u16 daily_year;
    u8 daily_month;
    u8 daily_day;
    u8 ophelia_anger;
    u8 ophelia_anger_total;
    u16 reserved_pins;
    u64 ophelia_anger_timestamp;

    s16 gammod_values[FNF_SAVE_GAMMOD_SLOTS];
    u8 reserved[192];
} FunkinSaveData;

void SaveData_Defaults(FunkinSaveData *data);
boolean SaveData_Init(void);
boolean SaveData_Load(FunkinSaveData *data);
boolean SaveData_Write(const FunkinSaveData *data);
void SaveData_GetProgression(const FunkinSaveData *data, ProgressionState *progression);
void SaveData_SetProgression(FunkinSaveData *data, const ProgressionState *progression);

#endif
