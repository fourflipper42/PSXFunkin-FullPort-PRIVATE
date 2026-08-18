#include "pointless_pins.h"

#include "asset_file.h"
#include "mem.h"
#include "random.h"
#include <math.h>
#include <string.h>

typedef struct PinCatalogHeader {
    char magic[4];
    u16 version;
    u16 rarity_count;
    u16 pin_count;
    u16 box_count;
    u32 rarity_size;
    u32 pin_size;
    u32 box_size;
    u32 chance_size;
    u32 chance_count;
    u32 string_bytes;
} __attribute__((packed)) PinCatalogHeader;

#define PIN_CATALOG_VERSION 1
#define PIN_NO_STRING 0xFFFFFFFFu
#define PIN_FLAG_SPECIAL (1u << 0)

static const float repeat_penalties[6] = {
    1.0f, 0.66f, 0.33f, 0.0f, -0.5f, -1.0f
};

static const char *pin_string(
    const PointlessPinsCatalog *catalog,
    u32 offset,
    boolean optional)
{
    const char *text;
    size_t left;

    if (optional && offset == PIN_NO_STRING)
        return NULL;
    if (catalog == NULL || catalog->strings == NULL || offset >= catalog->string_bytes)
        return NULL;
    text = catalog->strings + offset;
    left = catalog->string_bytes - offset;
    return memchr(text, '\0', left) != NULL ? text : NULL;
}

boolean PointlessPins_Load(PointlessPinsCatalog *catalog, const char *path)
{
    AssetFile file;
    PinCatalogHeader *header;
    size_t rarity_bytes;
    size_t pin_bytes;
    size_t box_bytes;
    size_t chance_bytes;
    size_t minimum;
    size_t got;
    u16 i;
    u32 j;
    u8 *cursor;

    if (catalog == NULL || path == NULL)
        return false;
    memset(catalog, 0, sizeof(*catalog));
    memset(&file, 0, sizeof(file));
    if (!AssetFile_Open(&file, path))
        return false;

    catalog->blob_size = AssetFile_Size(&file);
    if (catalog->blob_size < sizeof(PinCatalogHeader))
        goto fail;
    catalog->blob = Mem_Alloc(catalog->blob_size);
    if (catalog->blob == NULL)
        goto fail;
    got = AssetFile_Read(&file, catalog->blob, catalog->blob_size);
    AssetFile_Close(&file);
    if (got != catalog->blob_size)
        goto fail;

    header = (PinCatalogHeader *)catalog->blob;
    if (memcmp(header->magic, "FPIN", 4) != 0 ||
        header->version != PIN_CATALOG_VERSION ||
        header->rarity_size != sizeof(PinRarityRecord) ||
        header->pin_size != sizeof(PinRecord) ||
        header->box_size != sizeof(PinBoxRecord) ||
        header->chance_size != sizeof(PinChanceRecord) ||
        header->pin_count > FNF_SAVE_PIN_SLOTS ||
        header->box_count > FNF_SAVE_BOX_SLOTS)
        goto fail;

    rarity_bytes = (size_t)header->rarity_count * sizeof(PinRarityRecord);
    pin_bytes = (size_t)header->pin_count * sizeof(PinRecord);
    box_bytes = (size_t)header->box_count * sizeof(PinBoxRecord);
    chance_bytes = (size_t)header->chance_count * sizeof(PinChanceRecord);
    minimum = sizeof(PinCatalogHeader) + rarity_bytes + pin_bytes + box_bytes +
        chance_bytes + (size_t)header->string_bytes;
    if (minimum > catalog->blob_size)
        goto fail;

    cursor = (u8 *)catalog->blob + sizeof(PinCatalogHeader);
    catalog->rarities = (PinRarityRecord *)cursor;
    cursor += rarity_bytes;
    catalog->pins = (PinRecord *)cursor;
    cursor += pin_bytes;
    catalog->boxes = (PinBoxRecord *)cursor;
    cursor += box_bytes;
    catalog->chances = (PinChanceRecord *)cursor;
    cursor += chance_bytes;
    catalog->strings = (char *)cursor;
    catalog->rarity_count = header->rarity_count;
    catalog->pin_count = header->pin_count;
    catalog->box_count = header->box_count;
    catalog->chance_count = header->chance_count;
    catalog->string_bytes = header->string_bytes;

    for (i = 0; i < catalog->rarity_count; ++i) {
        const PinRarityRecord *rarity = &catalog->rarities[i];
        u32 end = (u32)rarity->first_pin + rarity->pin_count;
        if (end > catalog->pin_count || pin_string(catalog, rarity->name_offset, false) == NULL)
            goto fail;
    }
    for (i = 0; i < catalog->pin_count; ++i) {
        const PinRecord *pin = &catalog->pins[i];
        if (pin->rarity_index >= catalog->rarity_count ||
            pin_string(catalog, pin->id_offset, false) == NULL ||
            pin_string(catalog, pin->name_offset, false) == NULL ||
            (pin->description_offset != PIN_NO_STRING && pin_string(catalog, pin->description_offset, true) == NULL) ||
            (pin->locked_text_offset != PIN_NO_STRING && pin_string(catalog, pin->locked_text_offset, true) == NULL))
            goto fail;
    }
    for (i = 0; i < catalog->box_count; ++i) {
        const PinBoxRecord *box = &catalog->boxes[i];
        u32 end = (u32)box->chance_start + box->chance_count;
        if (end > catalog->chance_count ||
            pin_string(catalog, box->id_offset, false) == NULL ||
            pin_string(catalog, box->name_offset, false) == NULL ||
            pin_string(catalog, box->description_offset, false) == NULL)
            goto fail;
    }
    for (j = 0; j < catalog->chance_count; ++j) {
        if (catalog->chances[j].rarity_index >= catalog->rarity_count ||
            catalog->chances[j].weight == 0)
            goto fail;
    }

    catalog->loaded = true;
    return true;

fail:
    AssetFile_Close(&file);
    PointlessPins_Free(catalog);
    return false;
}

void PointlessPins_Free(PointlessPinsCatalog *catalog)
{
    if (catalog == NULL)
        return;
    if (catalog->blob != NULL)
        Mem_Free(catalog->blob);
    memset(catalog, 0, sizeof(*catalog));
}

const char *PointlessPins_PinId(const PointlessPinsCatalog *catalog, u16 index)
{
    if (catalog == NULL || !catalog->loaded || index >= catalog->pin_count)
        return NULL;
    return pin_string(catalog, catalog->pins[index].id_offset, false);
}

const char *PointlessPins_PinName(const PointlessPinsCatalog *catalog, u16 index)
{
    if (catalog == NULL || !catalog->loaded || index >= catalog->pin_count)
        return NULL;
    return pin_string(catalog, catalog->pins[index].name_offset, false);
}

const char *PointlessPins_BoxName(const PointlessPinsCatalog *catalog, u16 index)
{
    if (catalog == NULL || !catalog->loaded || index >= catalog->box_count)
        return NULL;
    return pin_string(catalog, catalog->boxes[index].name_offset, false);
}

boolean PointlessPins_IsOwned(const FunkinSaveData *save, u16 pin_index)
{
    return save != NULL && pin_index < FNF_SAVE_PIN_SLOTS && save->pin_counts[pin_index] != 0;
}

boolean PointlessPins_AwardPin(FunkinSaveData *save, u16 pin_index)
{
    if (save == NULL || pin_index >= FNF_SAVE_PIN_SLOTS)
        return false;
    if (save->pin_counts[pin_index] != 0xFFFFu)
        ++save->pin_counts[pin_index];
    return true;
}

static boolean select_pin_from_rarity(
    const PointlessPinsCatalog *catalog,
    u16 rarity_index,
    u16 *pin_index)
{
    const PinRarityRecord *rarity;
    u16 candidates[FNF_SAVE_PIN_SLOTS];
    u16 count = 0;
    u16 i;

    if (catalog == NULL || rarity_index >= catalog->rarity_count || pin_index == NULL)
        return false;
    rarity = &catalog->rarities[rarity_index];
    for (i = 0; i < rarity->pin_count; ++i) {
        u16 index = rarity->first_pin + i;
        if (index >= catalog->pin_count)
            break;
        if (catalog->pins[index].flags & PIN_FLAG_SPECIAL)
            continue;
        candidates[count++] = index;
    }
    if (count == 0)
        return false;
    *pin_index = candidates[(u16)RandomRange(0, count - 1)];
    return true;
}

boolean PointlessPins_BuyBox(
    const PointlessPinsCatalog *catalog,
    FunkinSaveData *save,
    u16 box_index,
    u16 *pin_index)
{
    const PinBoxRecord *box;
    u32 total = 0;
    u32 roll;
    u16 i;
    u16 rarity = 0xFFFFu;

    if (catalog == NULL || !catalog->loaded || save == NULL || pin_index == NULL ||
        box_index >= catalog->box_count)
        return false;
    box = &catalog->boxes[box_index];
    if (save->funkbucks < box->cost)
        return false;

    for (i = 0; i < box->chance_count; ++i)
        total += catalog->chances[box->chance_start + i].weight;
    if (total == 0)
        return false;

    roll = (u32)RandomRange(0, (s32)total - 1);
    for (i = 0; i < box->chance_count; ++i) {
        const PinChanceRecord *chance = &catalog->chances[box->chance_start + i];
        if (roll < chance->weight) {
            rarity = chance->rarity_index;
            break;
        }
        roll -= chance->weight;
    }
    if (rarity == 0xFFFFu || !select_pin_from_rarity(catalog, rarity, pin_index))
        return false;

    save->funkbucks -= box->cost;
    if (save->opened_box_counts[box_index] != 0xFFFFu)
        ++save->opened_box_counts[box_index];
    PointlessPins_AwardPin(save, *pin_index);
    return true;
}

u32 PointlessPins_HashCompletion(const char *completion_id)
{
    u32 hash = 2166136261u;
    if (completion_id == NULL)
        return 0;
    while (*completion_id != '\0') {
        hash ^= (u8)*completion_id++;
        hash *= 16777619u;
    }
    return hash == 0 ? 1 : hash;
}

static s8 repeat_count(const FunkinSaveData *save, u32 hash)
{
    s8 count = 0;
    int i;
    if (save == NULL || hash == 0)
        return 0;
    for (i = 0; i < FNF_SAVE_PREVIOUS_SONGS; ++i) {
        if (save->previous_song_hashes[i] == hash)
            ++count;
    }
    return count > 5 ? 5 : count;
}

static boolean consume_daily(FunkinSaveData *save, u32 hash)
{
    int i;
    if (save == NULL || hash == 0)
        return false;
    for (i = 0; i < FNF_SAVE_DAILY_SONGS; ++i) {
        if (save->daily_song_hashes[i] == hash) {
            save->daily_song_hashes[i] = 0;
            return true;
        }
    }
    return false;
}

static void remember_completion(FunkinSaveData *save, u32 hash)
{
    int i;
    if (save == NULL || hash == 0)
        return;
    for (i = FNF_SAVE_PREVIOUS_SONGS - 1; i > 0; --i)
        save->previous_song_hashes[i] = save->previous_song_hashes[i - 1];
    save->previous_song_hashes[0] = hash;
}

PointlessPinsReward PointlessPins_AwardSong(
    FunkinSaveData *save,
    const char *completion_id,
    s32 score,
    u32 total_notes,
    u32 sick_notes,
    boolean endless,
    u32 endless_loop)
{
    PointlessPinsReward result;
    u32 hash;
    float award;
    s8 repeats;
    boolean daily = false;
    s32 rounded;

    memset(&result, 0, sizeof(result));
    if (save == NULL || completion_id == NULL)
        return result;

    hash = PointlessPins_HashCompletion(completion_id);
    repeats = repeat_count(save, hash);
    award = (float)score / 2500.0f;

    if (total_notes != 0 && total_notes == sick_notes) {
        award *= 1.5f;
        result.all_sicks_bonus = true;
    }

    if (endless) {
        award *= 0.25f;
        result.endless_penalty = true;
    } else {
        daily = consume_daily(save, hash);
        if (daily) {
            award *= 1.5f;
            result.daily_bonus = true;
        } else {
            award *= repeat_penalties[(int)repeats];
        }
    }

    /* The source mod uses Math.ceil even for negative penalties. */
    rounded = (s32)ceilf(award);
    if (rounded >= 0) {
        save->funkbucks += (u32)rounded;
        save->funkbucks_lifetime += (u32)rounded;
    } else {
        u32 loss = (u32)(-rounded);
        save->funkbucks = loss > save->funkbucks ? 0 : save->funkbucks - loss;
    }

    /* Endless attempts before loop two deliberately do not clear repeats. */
    if (!(endless && endless_loop < 2u))
        remember_completion(save, hash);

    result.funkbucks = rounded;
    result.repeat_count = repeats;
    return result;
}
