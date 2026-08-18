#include "frontend.h"

#include "ps2_glyph.h"
#include <stdio.h>
#include <string.h>

#define FRONTEND_STORY_ROWS 10u
#define FRONTEND_SETTINGS_ROWS 9u
#define FRONTEND_GAMMOD_COUNT 35u
#define FRONTEND_HUD_COUNT 18u
#define FRONTEND_OPTION_COUNT 4u

static const char *page_name(FrontendPage page)
{
    switch (page) {
        case FRONTEND_STORY: return "STORY";
        case FRONTEND_FREEPLAY: return "FREEPLAY";
        case FRONTEND_PINS: return "POINTLESS PINS";
        case FRONTEND_GAMMOD: return "GAMMOD";
        case FRONTEND_HUD: return "CUSTOM HUD";
        case FRONTEND_OPTIONS: return "OPTIONS";
        default: return "FUNKIN";
    }
}

static u64 color_white(void) { return GS_SETREG_RGBAQ(0x80, 0x80, 0x80, 0x80, 0); }
static u64 color_dim(void) { return GS_SETREG_RGBAQ(0x50, 0x50, 0x60, 0x80, 0); }
static u64 color_accent(void) { return GS_SETREG_RGBAQ(0x80, 0x58, 0x78, 0x80, 0); }
static u64 color_locked(void) { return GS_SETREG_RGBAQ(0x48, 0x38, 0x3c, 0x80, 0); }

static const char *on_off(boolean value) { return value ? "ON" : "OFF"; }

static float clampf_local(float value, float low, float high)
{
    if (value < low) return low;
    if (value > high) return high;
    return value;
}

static int clampi_local(int value, int low, int high)
{
    if (value < low) return low;
    if (value > high) return high;
    return value;
}

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

static void move_selection(u8 *selection, u8 count, int direction)
{
    int value;
    if (selection == NULL || count == 0)
        return;
    value = (int)*selection + direction;
    while (value < 0) value += count;
    while (value >= count) value -= count;
    *selection = (u8)value;
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

static int setting_direction(const Pad *pad)
{
    if (pad == NULL)
        return 0;
    if (pad->press & PAD_LEFT) return -1;
    if (pad->press & (PAD_RIGHT | PAD_CROSS)) return 1;
    return 0;
}

static boolean adjust_bool(boolean *value, int direction)
{
    if (value == NULL || direction == 0)
        return false;
    *value = !*value;
    return true;
}

static FrontendAction update_gammod(
    Frontend *frontend,
    GammodConfig *config,
    const Pad *pad)
{
    FrontendAction action;
    int direction;
    boolean changed = false;
    memset(&action, 0, sizeof(action));
    if (frontend == NULL || config == NULL || pad == NULL)
        return action;

    if (pad->press & PAD_UP) move_selection(&frontend->gammod_selected, FRONTEND_GAMMOD_COUNT, -1);
    if (pad->press & PAD_DOWN) move_selection(&frontend->gammod_selected, FRONTEND_GAMMOD_COUNT, 1);
    direction = setting_direction(pad);
    if (direction == 0)
        return action;

    switch (frontend->gammod_selected) {
        case 0:
            config->autoplay = (GammodAutoPlay)(((int)config->autoplay + direction + 3) % 3);
            changed = true;
            break;
        case 1:
            config->long_notes = (GammodLongNotes)(((int)config->long_notes + direction + 4) % 4);
            changed = true;
            break;
        case 2:
            config->note_placement = (GammodNotePlacement)(((int)config->note_placement + direction + 3) % 3);
            changed = true;
            break;
        case 3:
            config->perfect_only = (GammodPerfectOnly)(((int)config->perfect_only + direction + 3) % 3);
            changed = true;
            break;
        case 4:
            config->player_side = (GammodPlayerSide)(((int)config->player_side + direction + 3) % 3);
            changed = true;
            break;
        case 5: changed = adjust_bool(&config->extra_notes, direction); break;
        case 6: changed = adjust_bool(&config->ghost_tapping, direction); break;
        case 7: changed = adjust_bool(&config->random_avoid_jacks, direction); break;
        case 8: changed = adjust_bool(&config->scroll_velocities, direction); break;
        case 9: changed = adjust_bool(&config->custom_scroll_speed_enabled, direction); break;
        case 10:
            config->custom_scroll_speed = clampf_local(config->custom_scroll_speed + direction * 0.1f, 0.1f, 20.0f);
            changed = true;
            break;
        case 11: changed = adjust_bool(&config->custom_scroll_opponent_separate, direction); break;
        case 12:
            config->custom_opponent_scroll_speed = clampf_local(config->custom_opponent_scroll_speed + direction * 0.1f, 0.1f, 20.0f);
            changed = true;
            break;
        case 13: changed = adjust_bool(&config->custom_scroll_as_multiplier, direction); break;
        case 14:
            config->health_drain = clampf_local(config->health_drain + direction * 0.5f, 0.0f, 66.0f);
            changed = true;
            break;
        case 15:
            config->health_gain = clampf_local(config->health_gain + direction * 0.1f, 0.0f, 66.0f);
            changed = true;
            break;
        case 16:
            config->health_loss = clampf_local(config->health_loss + direction * 0.1f, 0.0f, 25.0f);
            changed = true;
            break;
        case 17:
            config->playback_rate = clampf_local(config->playback_rate + direction * 0.05f, 0.5f, 3.0f);
            changed = true;
            break;
        case 18: changed = adjust_bool(&config->playback_stage_rate, direction); break;
        case 19: changed = adjust_bool(&config->playback_match_event_durations, direction); break;
        case 20: changed = adjust_bool(&config->playback_match_scroll_speed, direction); break;
        case 21: changed = adjust_bool(&config->custom_judgements, direction); break;
        case 22:
            config->sick_window_ms = (u16)clampi_local((int)config->sick_window_ms + direction, 1, 300);
            if (config->good_window_ms < config->sick_window_ms) config->good_window_ms = config->sick_window_ms;
            changed = true;
            break;
        case 23:
            config->good_window_ms = (u16)clampi_local((int)config->good_window_ms + direction, config->sick_window_ms, 350);
            if (config->bad_window_ms < config->good_window_ms) config->bad_window_ms = config->good_window_ms;
            changed = true;
            break;
        case 24:
            config->bad_window_ms = (u16)clampi_local((int)config->bad_window_ms + direction, config->good_window_ms, 400);
            if (config->shit_window_ms < config->bad_window_ms) config->shit_window_ms = config->bad_window_ms;
            changed = true;
            break;
        case 25:
            config->shit_window_ms = (u16)clampi_local((int)config->shit_window_ms + direction, config->bad_window_ms, 500);
            changed = true;
            break;
        case 26: changed = adjust_bool(&config->skip_countdown, direction); break;
        case 27:
            config->skip_countdown_delay = clampf_local(config->skip_countdown_delay + direction * 0.1f, 0.0f, 2.0f);
            changed = true;
            break;
        case 28:
            config->skip_silence = (GammodSkipSilence)(((int)config->skip_silence + direction + 2) % 2);
            changed = true;
            break;
        case 29:
            config->skip_safety_beats = (u8)clampi_local((int)config->skip_safety_beats + direction, 0, 8);
            changed = true;
            break;
        case 30: changed = adjust_bool(&config->skip_count_enemy_notes, direction); break;
        case 31:
            config->starting_health_percent = (u16)clampi_local((int)config->starting_health_percent + direction, 1, 100);
            changed = true;
            break;
        case 32: changed = adjust_bool(&config->reset_on_death, direction); break;
        case 33: changed = adjust_bool(&config->perfect_fail_on_ghost, direction); break;
        case 34: changed = adjust_bool(&config->autoplay_act_like_opponent, direction); break;
        default: break;
    }

    if (changed)
        action.type = FRONTEND_ACTION_SAVE_CHANGED;
    return action;
}

static void toggle_save_flag(FunkinSaveData *save, u32 flag)
{
    if (save != NULL)
        save->settings_flags ^= flag;
}

static FrontendAction update_hud(
    Frontend *frontend,
    FunkinSaveData *save,
    const Pad *pad)
{
    FrontendAction action;
    int direction;
    boolean changed = false;
    memset(&action, 0, sizeof(action));
    if (frontend == NULL || save == NULL || pad == NULL)
        return action;

    if (pad->press & PAD_UP) move_selection(&frontend->hud_selected, FRONTEND_HUD_COUNT, -1);
    if (pad->press & PAD_DOWN) move_selection(&frontend->hud_selected, FRONTEND_HUD_COUNT, 1);
    direction = setting_direction(pad);
    if (direction == 0)
        return action;

    switch (frontend->hud_selected) {
        case 0:
            save->hud_health_bar_opacity = (u8)clampi_local((int)save->hud_health_bar_opacity + direction * 5, 0, 100);
            changed = true;
            break;
        case 1:
            save->hud_icons_opacity = (u8)clampi_local((int)save->hud_icons_opacity + direction * 5, 0, 100);
            changed = true;
            break;
        case 2:
            save->hud_icons_position = (u8)(((int)save->hud_icons_position + direction + 3) % 3);
            changed = true;
            break;
        case 3: toggle_save_flag(save, SAVE_FLAG_HUD_FC_INDICATOR); changed = true; break;
        case 4:
            save->hud_fc_opacity = (u8)clampi_local((int)save->hud_fc_opacity + direction * 5, 0, 100);
            changed = true;
            break;
        case 5:
            save->hud_fc_size_tenths = (u8)clampi_local((int)save->hud_fc_size_tenths + direction, 5, 30);
            changed = true;
            break;
        case 6:
            save->hud_fc_style = save->hud_fc_style == 0 ? 1 : 0;
            changed = true;
            break;
        case 7: toggle_save_flag(save, SAVE_FLAG_HUD_ICON_BOUNCE); changed = true; break;
        case 8:
            save->hud_icon_bounce_style = save->hud_icon_bounce_style == 0 ? 1 : 0;
            changed = true;
            break;
        case 9: toggle_save_flag(save, SAVE_FLAG_HUD_SCORE_VISIBLE); changed = true; break;
        case 10:
            save->hud_score_position = (u8)(((int)save->hud_score_position + direction + 5) % 5);
            changed = true;
            break;
        case 11:
            save->hud_score_size = (u8)clampi_local((int)save->hud_score_size + direction * 2, 10, 72);
            changed = true;
            break;
        case 12:
            save->hud_combo_style = save->hud_combo_style == 0 ? 1 : 0;
            changed = true;
            break;
        case 13: toggle_save_flag(save, SAVE_FLAG_COMBO_POPUPS); changed = true; break;
        case 14: toggle_save_flag(save, SAVE_FLAG_COMBO_SWOOSH); changed = true; break;
        case 15: toggle_save_flag(save, SAVE_FLAG_COMBO_SOUND); changed = true; break;
        case 16: toggle_save_flag(save, SAVE_FLAG_COMBO_REVERSE_NUMBERS); changed = true; break;
        case 17:
            save->combo_swoosh_threshold = (u8)clampi_local((int)save->combo_swoosh_threshold + direction, 1, 99);
            changed = true;
            break;
        default: break;
    }

    if (changed)
        action.type = FRONTEND_ACTION_SAVE_CHANGED;
    return action;
}

static FrontendAction update_options(
    Frontend *frontend,
    FunkinSaveData *save,
    const Pad *pad)
{
    FrontendAction action;
    int direction;
    boolean changed = false;
    memset(&action, 0, sizeof(action));
    if (frontend == NULL || save == NULL || pad == NULL)
        return action;

    if (pad->press & PAD_UP) move_selection(&frontend->option_selected, FRONTEND_OPTION_COUNT, -1);
    if (pad->press & PAD_DOWN) move_selection(&frontend->option_selected, FRONTEND_OPTION_COUNT, 1);
    direction = setting_direction(pad);
    if (direction == 0)
        return action;

    switch (frontend->option_selected) {
        case 0: toggle_save_flag(save, SAVE_FLAG_CAMERA_MOVEMENT); changed = true; break;
        case 1: toggle_save_flag(save, SAVE_FLAG_CAMERA_ONLY_PLAYER); changed = true; break;
        case 2:
            save->camera_movement_intensity = (u8)clampi_local((int)save->camera_movement_intensity + direction, 0, 20);
            changed = true;
            break;
        case 3: toggle_save_flag(save, SAVE_FLAG_ENDLESS_DEFAULT); changed = true; break;
        default: break;
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
    GammodConfig *gammod,
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
        case FRONTEND_GAMMOD:
            return update_gammod(frontend, gammod, pad);
        case FRONTEND_HUD:
            return update_hud(frontend, save, pad);
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

static const char *gammod_autoplay_name(GammodAutoPlay value)
{
    switch (value) {
        case GAMMOD_AUTOPLAY_AUTO: return "AUTO";
        case GAMMOD_AUTOPLAY_CINEMA: return "CINEMA";
        default: return "DISABLED";
    }
}

static const char *gammod_long_name(GammodLongNotes value)
{
    switch (value) {
        case GAMMOD_LONG_NONE: return "NONE";
        case GAMMOD_LONG_ALL: return "ALL";
        case GAMMOD_LONG_INVERTED: return "INVERTED";
        default: return "NORMAL";
    }
}

static const char *gammod_placement_name(GammodNotePlacement value)
{
    switch (value) {
        case GAMMOD_PLACEMENT_MIRROR: return "MIRROR";
        case GAMMOD_PLACEMENT_RANDOM: return "RANDOM";
        default: return "NORMAL";
    }
}

static const char *gammod_perfect_name(GammodPerfectOnly value)
{
    switch (value) {
        case GAMMOD_PERFECT_PURPLE: return "PURPLE";
        case GAMMOD_PERFECT_GOLDEN: return "GOLDEN";
        default: return "DISABLED";
    }
}

static const char *gammod_side_name(GammodPlayerSide value)
{
    switch (value) {
        case GAMMOD_SIDE_OPPOSITE: return "OPPOSITE";
        case GAMMOD_SIDE_BOTH: return "BOTH";
        default: return "NORMAL";
    }
}

static void gammod_line(char *out, size_t out_size, u8 index, const GammodConfig *config)
{
    if (out == NULL || out_size == 0 || config == NULL)
        return;
    switch (index) {
        case 0: snprintf(out, out_size, "AUTOPLAY: %s", gammod_autoplay_name(config->autoplay)); break;
        case 1: snprintf(out, out_size, "LONG NOTES: %s", gammod_long_name(config->long_notes)); break;
        case 2: snprintf(out, out_size, "NOTE PLACEMENT: %s", gammod_placement_name(config->note_placement)); break;
        case 3: snprintf(out, out_size, "PERFECT ONLY: %s", gammod_perfect_name(config->perfect_only)); break;
        case 4: snprintf(out, out_size, "PLAYER SIDE: %s", gammod_side_name(config->player_side)); break;
        case 5: snprintf(out, out_size, "EXTRA NOTES: %s", on_off(config->extra_notes)); break;
        case 6: snprintf(out, out_size, "GHOST TAPPING: %s", on_off(config->ghost_tapping)); break;
        case 7: snprintf(out, out_size, "RANDOM AVOID JACKS: %s", on_off(config->random_avoid_jacks)); break;
        case 8: snprintf(out, out_size, "SCROLL VELOCITIES: %s", on_off(config->scroll_velocities)); break;
        case 9: snprintf(out, out_size, "CUSTOM SCROLL: %s", on_off(config->custom_scroll_speed_enabled)); break;
        case 10: snprintf(out, out_size, "PLAYER SCROLL: %.1fx", config->custom_scroll_speed); break;
        case 11: snprintf(out, out_size, "SEPARATE OPPONENT SCROLL: %s", on_off(config->custom_scroll_opponent_separate)); break;
        case 12: snprintf(out, out_size, "OPPONENT SCROLL: %.1fx", config->custom_opponent_scroll_speed); break;
        case 13: snprintf(out, out_size, "SCROLL AS MULTIPLIER: %s", on_off(config->custom_scroll_as_multiplier)); break;
        case 14: snprintf(out, out_size, "HEALTH DRAIN: %.1fx", config->health_drain); break;
        case 15: snprintf(out, out_size, "HEALTH GAIN: %.1fx", config->health_gain); break;
        case 16: snprintf(out, out_size, "HEALTH LOSS: %.1fx", config->health_loss); break;
        case 17: snprintf(out, out_size, "PLAYBACK RATE: %.2fx", config->playback_rate); break;
        case 18: snprintf(out, out_size, "MATCH STAGE RATE: %s", on_off(config->playback_stage_rate)); break;
        case 19: snprintf(out, out_size, "MATCH EVENT DURATIONS: %s", on_off(config->playback_match_event_durations)); break;
        case 20: snprintf(out, out_size, "MATCH SCROLL SPEED: %s", on_off(config->playback_match_scroll_speed)); break;
        case 21: snprintf(out, out_size, "CUSTOM JUDGEMENTS: %s", on_off(config->custom_judgements)); break;
        case 22: snprintf(out, out_size, "SICK WINDOW: %ums", (unsigned)config->sick_window_ms); break;
        case 23: snprintf(out, out_size, "GOOD WINDOW: %ums", (unsigned)config->good_window_ms); break;
        case 24: snprintf(out, out_size, "BAD WINDOW: %ums", (unsigned)config->bad_window_ms); break;
        case 25: snprintf(out, out_size, "SHIT WINDOW: %ums", (unsigned)config->shit_window_ms); break;
        case 26: snprintf(out, out_size, "SKIP COUNTDOWN: %s", on_off(config->skip_countdown)); break;
        case 27: snprintf(out, out_size, "COUNTDOWN DELAY: %.1fs", config->skip_countdown_delay); break;
        case 28: snprintf(out, out_size, "SKIP SILENCE: %s", config->skip_silence == GAMMOD_SKIP_SILENCE_INTRO ? "INTRO" : "DISABLED"); break;
        case 29: snprintf(out, out_size, "SILENCE SAFETY: %u BEATS", (unsigned)config->skip_safety_beats); break;
        case 30: snprintf(out, out_size, "COUNT ENEMY NOTES: %s", on_off(config->skip_count_enemy_notes)); break;
        case 31: snprintf(out, out_size, "STARTING HEALTH: %u%%", (unsigned)config->starting_health_percent); break;
        case 32: snprintf(out, out_size, "RESET ON DEATH: %s", on_off(config->reset_on_death)); break;
        case 33: snprintf(out, out_size, "PERFECT FAIL ON GHOST: %s", on_off(config->perfect_fail_on_ghost)); break;
        case 34: snprintf(out, out_size, "AUTOPLAY LIKE OPPONENT: %s", on_off(config->autoplay_act_like_opponent)); break;
        default: out[0] = '\0'; break;
    }
}

static void draw_scrolling_settings(
    GSGLOBAL *gs,
    Frontend *frontend,
    BetterAlphabet *alphabet,
    u8 selected,
    u8 count,
    void (*line_fn)(char *, size_t, u8, const void *),
    const void *context)
{
    u8 first;
    u8 row;
    char line[160];

    first = selected > FRONTEND_SETTINGS_ROWS / 2
        ? selected - FRONTEND_SETTINGS_ROWS / 2 : 0;
    if ((u16)first + FRONTEND_SETTINGS_ROWS > count && count > FRONTEND_SETTINGS_ROWS)
        first = count - FRONTEND_SETTINGS_ROWS;

    for (row = 0; row < FRONTEND_SETTINGS_ROWS; ++row) {
        u8 index = first + row;
        float y = 122.0f + row * 27.0f;
        if (index >= count)
            break;
        line_fn(line, sizeof(line), index, context);
        if (index == selected)
            gsKit_prim_sprite(gs, 44.0f, y - 4.0f, 596.0f, y + 20.0f, 3,
                GS_SETREG_RGBAQ(0x48, 0x32, 0x5a, 0x80, 0));
        print_text(gs, frontend, alphabet, 54.0f, y, 0.36f, 5, color_white(), line);
    }
    print_text(gs, frontend, alphabet, 52.0f, 370.0f, 0.31f, 5, color_dim(), "UP/DOWN SELECT   LEFT/RIGHT OR CROSS CHANGE");
}

static void gammod_line_bridge(char *out, size_t out_size, u8 index, const void *context)
{
    gammod_line(out, out_size, index, (const GammodConfig *)context);
}

static void draw_gammod(
    GSGLOBAL *gs,
    Frontend *frontend,
    const GammodConfig *config,
    BetterAlphabet *alphabet)
{
    if (config == NULL)
        return;
    draw_scrolling_settings(gs, frontend, alphabet,
        frontend->gammod_selected, FRONTEND_GAMMOD_COUNT,
        gammod_line_bridge, config);
}

static const char *icon_position_name(u8 value)
{
    if (value == 1) return "CORNERS";
    if (value == 2) return "CLASSIC";
    return "DEFAULT";
}

static const char *score_position_name(u8 value)
{
    switch (value) {
        case 1: return "CLASSIC";
        case 2: return "TOP LEFT";
        case 3: return "BOTTOM LEFT";
        case 4: return "BOTTOM RIGHT";
        default: return "HUD";
    }
}

static void hud_line(char *out, size_t out_size, u8 index, const FunkinSaveData *save)
{
    if (out == NULL || out_size == 0 || save == NULL)
        return;
    switch (index) {
        case 0: snprintf(out, out_size, "HEALTH BAR OPACITY: %u%%", (unsigned)save->hud_health_bar_opacity); break;
        case 1: snprintf(out, out_size, "ICON OPACITY: %u%%", (unsigned)save->hud_icons_opacity); break;
        case 2: snprintf(out, out_size, "ICON POSITION: %s", icon_position_name(save->hud_icons_position)); break;
        case 3: snprintf(out, out_size, "FC INDICATOR: %s", on_off((save->settings_flags & SAVE_FLAG_HUD_FC_INDICATOR) != 0)); break;
        case 4: snprintf(out, out_size, "FC OPACITY: %u%%", (unsigned)save->hud_fc_opacity); break;
        case 5: snprintf(out, out_size, "FC SIZE: %.1fx", (float)save->hud_fc_size_tenths / 10.0f); break;
        case 6: snprintf(out, out_size, "FC STYLE: %s", save->hud_fc_style == 1 ? "DEATH" : "FC"); break;
        case 7: snprintf(out, out_size, "ICON BOUNCE: %s", on_off((save->settings_flags & SAVE_FLAG_HUD_ICON_BOUNCE) != 0)); break;
        case 8: snprintf(out, out_size, "BOUNCE STYLE: %s", save->hud_icon_bounce_style == 1 ? "CLASSIC" : "REWORKED"); break;
        case 9: snprintf(out, out_size, "SCORE TEXT: %s", on_off((save->settings_flags & SAVE_FLAG_HUD_SCORE_VISIBLE) != 0)); break;
        case 10: snprintf(out, out_size, "SCORE POSITION: %s", score_position_name(save->hud_score_position)); break;
        case 11: snprintf(out, out_size, "SCORE SIZE: %u", (unsigned)save->hud_score_size); break;
        case 12: snprintf(out, out_size, "COMBO STYLE: %s", save->hud_combo_style == 1 ? "WORLD" : "DUSTIN"); break;
        case 13: snprintf(out, out_size, "COMBO POPUPS: %s", on_off((save->settings_flags & SAVE_FLAG_COMBO_POPUPS) != 0)); break;
        case 14: snprintf(out, out_size, "COMBO SWOOSH: %s", on_off((save->settings_flags & SAVE_FLAG_COMBO_SWOOSH) != 0)); break;
        case 15: snprintf(out, out_size, "COMBO SOUND: %s", on_off((save->settings_flags & SAVE_FLAG_COMBO_SOUND) != 0)); break;
        case 16: snprintf(out, out_size, "REVERSE COMBO NUMBERS: %s", on_off((save->settings_flags & SAVE_FLAG_COMBO_REVERSE_NUMBERS) != 0)); break;
        case 17: snprintf(out, out_size, "SWOOSH THRESHOLD: %u", (unsigned)save->combo_swoosh_threshold); break;
        default: out[0] = '\0'; break;
    }
}

static void hud_line_bridge(char *out, size_t out_size, u8 index, const void *context)
{
    hud_line(out, out_size, index, (const FunkinSaveData *)context);
}

static void draw_hud(
    GSGLOBAL *gs,
    Frontend *frontend,
    const FunkinSaveData *save,
    BetterAlphabet *alphabet)
{
    if (save == NULL)
        return;
    draw_scrolling_settings(gs, frontend, alphabet,
        frontend->hud_selected, FRONTEND_HUD_COUNT,
        hud_line_bridge, save);
}

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
    snprintf(lines[1], sizeof(lines[1]), "CAMERA ONLY PLAYER: %s", on_off((save->settings_flags & SAVE_FLAG_CAMERA_ONLY_PLAYER) != 0));
    snprintf(lines[2], sizeof(lines[2]), "CAMERA INTENSITY: %u", (unsigned)save->camera_movement_intensity);
    snprintf(lines[3], sizeof(lines[3]), "ENDLESS DEFAULT: %s", on_off((save->settings_flags & SAVE_FLAG_ENDLESS_DEFAULT) != 0));

    for (i = 0; i < FRONTEND_OPTION_COUNT; ++i) {
        float y = 125.0f + i * 30.0f;
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
    const GammodConfig *gammod,
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
            case FRONTEND_GAMMOD:
                draw_gammod(gs, frontend, gammod, alphabet);
                break;
            case FRONTEND_HUD:
                draw_hud(gs, frontend, save, alphabet);
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
