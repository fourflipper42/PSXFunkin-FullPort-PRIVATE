#include "frontend.h"

#include "ps2_glyph.h"
#include <stdio.h>
#include <string.h>

#define FRONTEND_STORY_ROWS 10u
#define FRONTEND_OPTION_COUNT 7u

static const char *page_name(FrontendPage page)
{
    switch (page) {
        case FRONTEND_STORY: return "STORY";
        case FRONTEND_FREEPLAY: return "FREEPLAY";
        case FRONTEND_PINS: return "POINTLESS PINS";
        case FRONTEND_OPTIONS: return "OPTIONS";
        default: return "FUNKIN";
    }
}

static u64 color_white(void) { return GS_SETREG_RGBAQ(0x80, 0x80, 0x80, 0x80, 0); }
static u64 color_dim(void) { return GS_SETREG_RGBAQ(0x50, 0x50, 0x60, 0x80, 0); }
static u64 color_accent(void) { return GS_SETREG_RGBAQ(0x80, 0x58, 0x78, 0x80, 0); }
static u64 color_locked(void) { return GS_SETREG_RGBAQ(0x48, 0x38, 0x3c, 0x80, 0); }

static void print_text(
    GSGLOBAL *gs,
    Frontend *frontend,
    BetterAlphabet *alphabet,
    float x,
    float y,
    float scale,
    int z,
    u64 color,
    const char *text)
{
    if (alphabet != NULL && alphabet->loaded) {
        (void)color;
        BetterAlphabet_Draw(gs, alphabet, x, y, scale * 1.1f, z, text);
    } else if (frontend != NULL && frontend->font_ready && frontend->rom_font != NULL) {
        gsKit_fontm_print_scaled(gs, frontend->rom_font, x, y, z, scale, color, text);
    }
}

static void move_page(Frontend *frontend, int direction)
{
    int page;
    if (frontend == NULL)
        return;
    page = (int)frontend->page + direction;
    while (page < 0) page += FRONTEND_PAGE_COUNT;
    while (page >= FRONTEND_PAGE_COUNT) page -= FRONTEND_PAGE_COUNT;
    frontend->page = (FrontendPage)page;
}

static boolean visible_level(const StoryCatalog *story, u16 index)
{
    StoryLevelEntry level;
    return StoryCatalog_GetLevel(story, index, &level) &&
        (level.flags & STORY_LEVEL_VISIBLE) != 0;
}

static void move_story_level(Frontend *frontend, const StoryCatalog *story, int direction)
{
    u16 current;
    u16 attempts;
    if (frontend == NULL || story == NULL || !story->loaded || story->level_count == 0)
        return;
    current = frontend->story_selected;
    for (attempts = 0; attempts < story->level_count; ++attempts) {
        if (direction < 0)
            current = current == 0 ? story->level_count - 1 : current - 1;
        else
            current = (u16)((current + 1u) % story->level_count);
        if (visible_level(story, current)) {
            frontend->story_selected = current;
            return;
        }
    }
}

static void move_story_difficulty(
    Frontend *frontend,
    const StoryCatalog *story,
    const SongCatalog *songs,
    int direction)
{
    int value;
    int attempts;
    if (frontend == NULL)
        return;
    value = (int)frontend->story_difficulty;
    for (attempts = 0; attempts < STORY_DIFFICULTY_COUNT; ++attempts) {
        value += direction;
        if (value < 0) value = STORY_DIFFICULTY_COUNT - 1;
        if (value >= STORY_DIFFICULTY_COUNT) value = 0;
        if (StorySession_LevelSupportsDifficulty(
            story, songs, frontend->story_selected, (StoryDifficulty)value)) {
            frontend->story_difficulty = (StoryDifficulty)value;
            return;
        }
    }
}

static boolean pico_unlocked(
    const ProgressionState *progression,
    const StoryCatalog *story)
{
    return Progression_PicoUnlocked(progression, story);
}

static boolean find_pico_song(
    const SongCatalog *songs,
    const SongCatalogEntry *selected,
    SongCatalogEntry *result)
{
    static const char *pico_variations[] = {"pico", "pico-mix", "picoMix"};
    size_t i;
    if (songs == NULL || selected == NULL || result == NULL)
        return false;
    for (i = 0; i < sizeof(pico_variations) / sizeof(pico_variations[0]); ++i) {
        if (SongCatalog_Find(
            songs,
            selected->song_id,
            pico_variations[i],
            selected->difficulty,
            result))
            return true;
    }
    return false;
}

void Frontend_Init(Frontend *frontend, GSFONTM *rom_font)
{
    if (frontend == NULL)
        return;
    memset(frontend, 0, sizeof(*frontend));
    frontend->page = FRONTEND_STORY;
    frontend->player = FRONTEND_PLAYER_BF;
    frontend->story_difficulty = STORY_DIFFICULTY_NORMAL;
    frontend->rom_font = rom_font;
    frontend->font_ready = rom_font != NULL;
}

static FrontendAction update_story(
    Frontend *frontend,
    const SongCatalog *songs,
    const StoryCatalog *story,
    const ProgressionState *progression,
    const Pad *pad)
{
    FrontendAction action;
    memset(&action, 0, sizeof(action));
    if (story == NULL || !story->loaded || songs == NULL || !songs->loaded)
        return action;

    if (pad->press & PAD_UP) move_story_level(frontend, story, -1);
    if (pad->press & PAD_DOWN) move_story_level(frontend, story, 1);
    if (pad->press & PAD_LEFT) move_story_difficulty(frontend, story, songs, -1);
    if (pad->press & PAD_RIGHT) move_story_difficulty(frontend, story, songs, 1);

    if (pad->press & PAD_CROSS) {
        if (Progression_IsLevelUnlocked(progression, story, frontend->story_selected) &&
            StorySession_LevelSupportsDifficulty(
                story, songs, frontend->story_selected, frontend->story_difficulty)) {
            action.type = FRONTEND_ACTION_LAUNCH_STORY;
            action.story_level = frontend->story_selected;
            action.story_difficulty = frontend->story_difficulty;
        }
    }
    return action;
}

static FrontendAction update_freeplay(
    Frontend *frontend,
    FreeplayBrowser *freeplay,
    const SongCatalog *songs,
    const StoryCatalog *story,
    const ProgressionState *progression,
    const Pad *pad)
{
    FrontendAction action;
    SongCatalogEntry selected;
    memset(&action, 0, sizeof(action));
    FreeplayBrowser_Update(freeplay, songs, pad);

    if (pad->press & PAD_TRIANGLE) {
        if (pico_unlocked(progression, story))
            frontend->player = frontend->player == FRONTEND_PLAYER_BF
                ? FRONTEND_PLAYER_PICO : FRONTEND_PLAYER_BF;
        else
            frontend->player = FRONTEND_PLAYER_BF;
    }

    if ((pad->press & PAD_CROSS) &&
        FreeplayBrowser_Selected(freeplay, songs, &selected)) {
        action.type = FRONTEND_ACTION_LAUNCH_FREEPLAY;
        action.song = selected;
        if (frontend->player == FRONTEND_PLAYER_PICO) {
            SongCatalogEntry pico;
            if (find_pico_song(songs, &selected, &pico))
                action.song = pico;
        }
    }
    return action;
}

static FrontendAction update_pins(
    Frontend *frontend,
    const PointlessPinsCatalog *pins,
    const Pad *pad)
{
    FrontendAction action;
    memset(&action, 0, sizeof(action));
    if (pins == NULL || !pins->loaded || pins->box_count == 0)
        return action;
    if (pad->press & PAD_UP) {
        frontend->pin_box_selected = frontend->pin_box_selected == 0
            ? pins->box_count - 1 : frontend->pin_box_selected - 1;
    }
    if (pad->press & PAD_DOWN)
        frontend->pin_box_selected = (u16)((frontend->pin_box_selected + 1u) % pins->box_count);
    if (pad->press & PAD_CROSS) {
        action.type = FRONTEND_ACTION_BUY_BOX;
        action.box_index = frontend->pin_box_selected;
    }
    return action;
}

static FrontendAction update_options(
    Frontend *frontend,
    FunkinSaveData *save,
    const Pad *pad)
{
    FrontendAction action;
    boolean changed = false;
    memset(&action, 0, sizeof(action));
    if (save == NULL)
        return action;

    if (pad->press & PAD_UP)
        frontend->option_selected = frontend->option_selected == 0
            ? FRONTEND_OPTION_COUNT - 1 : frontend->option_selected - 1;
    if (pad->press & PAD_DOWN)
        frontend->option_selected = (u8)((frontend->option_selected + 1u) % FRONTEND_OPTION_COUNT);

    if (pad->press & (PAD_LEFT | PAD_RIGHT | PAD_CROSS)) {
        int direction = (pad->press & PAD_LEFT) ? -1 : 1;
        switch (frontend->option_selected) {
            case 0:
                save->settings_flags ^= SAVE_FLAG_CAMERA_MOVEMENT;
                changed = true;
                break;
            case 1:
                save->settings_flags ^= SAVE_FLAG_ENDLESS_DEFAULT;
                changed = true;
                break;
            case 2:
                save->settings_flags ^= SAVE_FLAG_COMBO_POPUPS;
                changed = true;
                break;
            case 3:
                save->settings_flags ^= SAVE_FLAG_COMBO_SWOOSH;
                changed = true;
                break;
            case 4:
                save->hud_icons_position = (u8)((save->hud_icons_position + direction + 3) % 3);
                changed = true;
                break;
            case 5:
                save->settings_flags ^= SAVE_FLAG_HUD_SCORE_VISIBLE;
                changed = true;
                break;
            case 6:
                save->hud_combo_style = save->hud_combo_style == 0 ? 1 : 0;
                changed = true;
                break;
        }
    }
    if (changed)
        action.type = FRONTEND_ACTION_SAVE_CHANGED;
    return action;
}

FrontendAction Frontend_Update(
    Frontend *frontend,
    FreeplayBrowser *freeplay,
    const SongCatalog *songs,
    const StoryCatalog *story,
    const ProgressionState *progression,
    const PointlessPinsCatalog *pins,
    FunkinSaveData *save,
    const Pad *pad)
{
    FrontendAction action;
    memset(&action, 0, sizeof(action));
    if (frontend == NULL || pad == NULL)
        return action;

    if (pad->press & PAD_L2) move_page(frontend, -1);
    if (pad->press & PAD_R2) move_page(frontend, 1);

    switch (frontend->page) {
        case FRONTEND_STORY:
            return update_story(frontend, songs, story, progression, pad);
        case FRONTEND_FREEPLAY:
            return update_freeplay(frontend, freeplay, songs, story, progression, pad);
        case FRONTEND_PINS:
            return update_pins(frontend, pins, pad);
        case FRONTEND_OPTIONS:
            return update_options(frontend, save, pad);
        default:
            return action;
    }
}

static void draw_header(
    GSGLOBAL *gs,
    Frontend *frontend,
    BetterAlphabet *alphabet,
    const StoryCatalog *story,
    const ProgressionState *progression)
{
    char line[128];
    boolean pico = pico_unlocked(progression, story);
    print_text(gs, frontend, alphabet, 44.0f, 64.0f, 0.55f, 5, color_accent(), page_name(frontend->page));
    snprintf(line, sizeof(line), "PLAYER: %s%s",
        frontend->player == FRONTEND_PLAYER_PICO ? "PICO" : "BOYFRIEND",
        pico ? "" : "  [PICO LOCKED: CLEAR WEEKEND 1]");
    print_text(gs, frontend, alphabet, 44.0f, 89.0f, 0.35f, 5, color_dim(), line);
}

static void draw_story(
    GSGLOBAL *gs,
    Frontend *frontend,
    const SongCatalog *songs,
    const StoryCatalog *story,
    const ProgressionState *progression,
    BetterAlphabet *alphabet)
{
    u16 first;
    u16 row;
    char line[180];

    if (story == NULL || !story->loaded) {
        print_text(gs, frontend, alphabet, 58.0f, 175.0f, 0.48f, 5, color_white(), "NO STORY CATALOG");
        return;
    }

    first = frontend->story_selected > FRONTEND_STORY_ROWS / 2
        ? frontend->story_selected - FRONTEND_STORY_ROWS / 2 : 0;
    if ((u32)first + FRONTEND_STORY_ROWS > story->level_count && story->level_count > FRONTEND_STORY_ROWS)
        first = story->level_count - FRONTEND_STORY_ROWS;

    for (row = 0; row < FRONTEND_STORY_ROWS; ++row) {
        u16 index = first + row;
        StoryLevelEntry level;
        float y = 118.0f + row * 22.0f;
        boolean unlocked;
        if (index >= story->level_count || !StoryCatalog_GetLevel(story, index, &level) ||
            !(level.flags & STORY_LEVEL_VISIBLE))
            continue;
        unlocked = Progression_IsLevelUnlocked(progression, story, index);
        if (index == frontend->story_selected)
            gsKit_prim_sprite(gs, 42.0f, y - 3.0f, 598.0f, y + 17.0f, 3,
                unlocked ? GS_SETREG_RGBAQ(0x58, 0x30, 0x68, 0x80, 0) : GS_SETREG_RGBAQ(0x38, 0x28, 0x30, 0x80, 0));
        snprintf(line, sizeof(line), "%s%s%s",
            unlocked ? "" : "[LOCKED] ",
            level.name,
            Progression_IsLevelComplete(progression, index) ? "  [CLEARED]" : "");
        print_text(gs, frontend, alphabet, 52.0f, y, 0.40f, 5,
            unlocked ? color_white() : color_locked(), line);
    }

    snprintf(line, sizeof(line), "DIFFICULTY: %s%s",
        StoryDifficulty_Name(frontend->story_difficulty),
        StorySession_LevelSupportsDifficulty(story, songs, frontend->story_selected, frontend->story_difficulty)
            ? "" : "  [UNAVAILABLE]");
    print_text(gs, frontend, alphabet, 52.0f, 344.0f, 0.36f, 5, color_dim(), line);
}

static void draw_freeplay_overlay(
    GSGLOBAL *gs,
    Frontend *frontend,
    const StoryCatalog *story,
    const ProgressionState *progression,
    BetterAlphabet *alphabet)
{
    const char *hint = pico_unlocked(progression, story)
        ? "TRIANGLE: SWITCH BOYFRIEND / PICO"
        : "PICO UNLOCKS AFTER WEEKEND 1";
    print_text(gs, frontend, alphabet, 44.0f, 378.0f, 0.33f, 7, color_dim(), hint);
}

static void draw_pins(
    GSGLOBAL *gs,
    Frontend *frontend,
    const PointlessPinsCatalog *pins,
    const FunkinSaveData *save,
    BetterAlphabet *alphabet)
{
    u16 i;
    char line[180];
    if (pins == NULL || !pins->loaded || save == NULL) {
        print_text(gs, frontend, alphabet, 58.0f, 175.0f, 0.48f, 5, color_white(), "POINTLESS PINS DATA NOT FOUND");
        return;
    }
    snprintf(line, sizeof(line), "FUNKBUCKS: %d", (int)save->funkbucks);
    print_text(gs, frontend, alphabet, 52.0f, 120.0f, 0.50f, 5, color_white(), line);
    for (i = 0; i < pins->box_count; ++i) {
        const PinBoxRecord *box = &pins->boxes[i];
        float y = 162.0f + i * 30.0f;
        if (i == frontend->pin_box_selected)
            gsKit_prim_sprite(gs, 44.0f, y - 4.0f, 596.0f, y + 20.0f, 3,
                GS_SETREG_RGBAQ(0x48, 0x32, 0x5a, 0x80, 0));
        snprintf(line, sizeof(line), "%s  COST %u  OPENED %u",
            PointlessPins_BoxName(pins, i),
            (unsigned)box->cost,
            (unsigned)save->opened_box_counts[i]);
        print_text(gs, frontend, alphabet, 54.0f, y, 0.40f, 5, color_white(), line);
    }
    print_text(gs, frontend, alphabet, 52.0f, 344.0f, 0.34f, 5, color_dim(), "CROSS: BUY BOX");
}

static const char *on_off(boolean value) { return value ? "ON" : "OFF"; }

static void draw_options(
    GSGLOBAL *gs,
    Frontend *frontend,
    const FunkinSaveData *save,
    BetterAlphabet *alphabet)
{
    char lines[FRONTEND_OPTION_COUNT][128];
    u8 i;
    if (save == NULL)
        return;
    snprintf(lines[0], sizeof(lines[0]), "CAMERA MOVEMENTS: %s", on_off((save->settings_flags & SAVE_FLAG_CAMERA_MOVEMENT) != 0));
    snprintf(lines[1], sizeof(lines[1]), "ENDLESS DEFAULT: %s", on_off((save->settings_flags & SAVE_FLAG_ENDLESS_DEFAULT) != 0));
    snprintf(lines[2], sizeof(lines[2]), "COMBO POPUPS: %s", on_off((save->settings_flags & SAVE_FLAG_COMBO_POPUPS) != 0));
    snprintf(lines[3], sizeof(lines[3]), "COMBO SWOOSH: %s", on_off((save->settings_flags & SAVE_FLAG_COMBO_SWOOSH) != 0));
    snprintf(lines[4], sizeof(lines[4]), "ICON POSITION: %s",
        save->hud_icons_position == 1 ? "CORNERS" : (save->hud_icons_position == 2 ? "CLASSIC" : "DEFAULT"));
    snprintf(lines[5], sizeof(lines[5]), "SCORE TEXT: %s", on_off((save->settings_flags & SAVE_FLAG_HUD_SCORE_VISIBLE) != 0));
    snprintf(lines[6], sizeof(lines[6]), "COMBO STYLE: %s", save->hud_combo_style == 1 ? "WORLD" : "DUSTIN");

    for (i = 0; i < FRONTEND_OPTION_COUNT; ++i) {
        float y = 125.0f + i * 27.0f;
        if (i == frontend->option_selected)
            gsKit_prim_sprite(gs, 44.0f, y - 4.0f, 596.0f, y + 20.0f, 3,
                GS_SETREG_RGBAQ(0x48, 0x32, 0x5a, 0x80, 0));
        print_text(gs, frontend, alphabet, 54.0f, y, 0.41f, 5, color_white(), lines[i]);
    }
}

void Frontend_Draw(
    GSGLOBAL *gs,
    Frontend *frontend,
    const FreeplayBrowser *freeplay,
    const SongCatalog *songs,
    const StoryCatalog *story,
    const ProgressionState *progression,
    const PointlessPinsCatalog *pins,
    const FunkinSaveData *save,
    BetterAlphabet *alphabet)
{
    const u64 black = GS_SETREG_RGBAQ(0x00, 0x00, 0x00, 0x80, 0);
    const u64 bg = GS_SETREG_RGBAQ(0x18, 0x14, 0x28, 0x80, 0);
    const u64 panel = GS_SETREG_RGBAQ(0x24, 0x20, 0x34, 0x80, 0);

    if (gs == NULL || frontend == NULL)
        return;

    if (frontend->page == FRONTEND_FREEPLAY && freeplay != NULL && songs != NULL) {
        FreeplayBrowser_Draw(gs, freeplay, songs);
        draw_freeplay_overlay(gs, frontend, story, progression, alphabet);
    } else {
        gsKit_clear(gs, black);
        gsKit_prim_sprite(gs, 0.0f, 44.0f, 640.0f, 404.0f, 1, bg);
        gsKit_prim_sprite(gs, 28.0f, 56.0f, 612.0f, 388.0f, 2, panel);
        draw_header(gs, frontend, alphabet, story, progression);
        switch (frontend->page) {
            case FRONTEND_STORY:
                draw_story(gs, frontend, songs, story, progression, alphabet);
                break;
            case FRONTEND_PINS:
                draw_pins(gs, frontend, pins, save, alphabet);
                break;
            case FRONTEND_OPTIONS:
                draw_options(gs, frontend, save, alphabet);
                break;
            default:
                break;
        }
    }

    Ps2Glyph_Draw(gs, PS2_GLYPH_L2, 34.0f, 404.0f, 18.0f, 8);
    Ps2Glyph_Draw(gs, PS2_GLYPH_R2, 78.0f, 404.0f, 18.0f, 8);
    Ps2Glyph_Draw(gs, PS2_GLYPH_CROSS, 528.0f, 406.0f, 18.0f, 8);
    if (frontend->page == FRONTEND_FREEPLAY)
        Ps2Glyph_Draw(gs, PS2_GLYPH_TRIANGLE, 570.0f, 406.0f, 18.0f, 8);
}

boolean Frontend_PicoSelected(const Frontend *frontend)
{
    return frontend != NULL && frontend->player == FRONTEND_PLAYER_PICO;
}
