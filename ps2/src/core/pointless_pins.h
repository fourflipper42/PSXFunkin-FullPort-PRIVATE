#ifndef FNF_PS2_POINTLESS_PINS_H
#define FNF_PS2_POINTLESS_PINS_H

#include "fixed.h"
#include "save_data.h"
#include <stddef.h>

typedef struct PinRarityRecord {
    u32 name_offset;
    u32 color;
    u16 first_pin;
    u16 pin_count;
} __attribute__((packed)) PinRarityRecord;

typedef struct PinRecord {
    u32 id_offset;
    u32 name_offset;
    u32 description_offset;
    u32 locked_text_offset;
    float scale;
    u16 rarity_index;
    u16 flags;
} __attribute__((packed)) PinRecord;

typedef struct PinBoxRecord {
    u32 id_offset;
    u32 name_offset;
    u32 description_offset;
    u16 cost;
    u16 reveal_time;
    u16 chance_start;
    u16 chance_count;
    u32 flags;
} __attribute__((packed)) PinBoxRecord;

typedef struct PinChanceRecord {
    u16 rarity_index;
    u16 weight;
} __attribute__((packed)) PinChanceRecord;

typedef struct PointlessPinsCatalog {
    void *blob;
    size_t blob_size;
    PinRarityRecord *rarities;
    PinRecord *pins;
    PinBoxRecord *boxes;
    PinChanceRecord *chances;
    char *strings;
    u32 string_bytes;
    u32 chance_count;
    u16 rarity_count;
    u16 pin_count;
    u16 box_count;
    boolean loaded;
} PointlessPinsCatalog;

typedef struct PointlessPinsReward {
    s32 funkbucks;
    s8 repeat_count;
    boolean all_sicks_bonus;
    boolean daily_bonus;
    boolean endless_penalty;
} PointlessPinsReward;

boolean PointlessPins_Load(PointlessPinsCatalog *catalog, const char *path);
void PointlessPins_Free(PointlessPinsCatalog *catalog);
const char *PointlessPins_PinId(const PointlessPinsCatalog *catalog, u16 index);
const char *PointlessPins_PinName(const PointlessPinsCatalog *catalog, u16 index);
const char *PointlessPins_BoxName(const PointlessPinsCatalog *catalog, u16 index);
boolean PointlessPins_IsOwned(const FunkinSaveData *save, u16 pin_index);
boolean PointlessPins_AwardPin(FunkinSaveData *save, u16 pin_index);
boolean PointlessPins_BuyBox(
    const PointlessPinsCatalog *catalog,
    FunkinSaveData *save,
    u16 box_index,
    u16 *pin_index);
PointlessPinsReward PointlessPins_AwardSong(
    FunkinSaveData *save,
    const char *completion_id,
    s32 score,
    u32 total_notes,
    u32 sick_notes,
    boolean endless,
    u32 endless_loop);
u32 PointlessPins_HashCompletion(const char *completion_id);

#endif
