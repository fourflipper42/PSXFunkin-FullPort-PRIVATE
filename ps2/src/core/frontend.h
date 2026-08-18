#ifndef FNF_PS2_FRONTEND_H
#define FNF_PS2_FRONTEND_H

#include "better_alphabet.h"
#include "freeplay_browser.h"
#include "gammod.h"
#include "pointless_pins.h"
#include "progression.h"
#include "save_data.h"
#include "song_catalog.h"
#include "story_catalog.h"
#include "story_session.h"

typedef enum FrontendPage {
    FRONTEND_STORY = 0,
    FRONTEND_FREEPLAY,
    FRONTEND_PINS,
    FRONTEND_GAMMOD,
    FRONTEND_HUD,
    FRONTEND_OPTIONS,
    FRONTEND_PAGE_COUNT
} FrontendPage;

typedef enum FrontendScreen {
    FRONTEND_SCREEN_TITLE = 0,
    FRONTEND_SCREEN_MAIN,
    FRONTEND_SCREEN_PAGE,
    FRONTEND_SCREEN_CHARACTER,
    FRONTEND_SCREEN_EXTRAS
} FrontendScreen;

typedef enum FrontendMainItem {
    FRONTEND_MAIN_STORY = 0,
    FRONTEND_MAIN_FREEPLAY,
    FRONTEND_MAIN_CHARACTER,
    FRONTEND_MAIN_OPTIONS,
    FRONTEND_MAIN_EXTRAS,
    FRONTEND_MAIN_COUNT
} FrontendMainItem;

typedef enum FrontendExtraItem {
    FRONTEND_EXTRA_GAMMOD = 0,
    FRONTEND_EXTRA_HUD,
    FRONTEND_EXTRA_PINS,
    FRONTEND_EXTRA_COUNT
} FrontendExtraItem;

typedef enum FrontendPlayer {
    FRONTEND_PLAYER_BF = 0,
    FRONTEND_PLAYER_PICO
} FrontendPlayer;

typedef enum FrontendActionType {
    FRONTEND_ACTION_NONE = 0,
    FRONTEND_ACTION_LAUNCH_FREEPLAY,
    FRONTEND_ACTION_LAUNCH_STORY,
    FRONTEND_ACTION_BUY_BOX,
    FRONTEND_ACTION_SAVE_CHANGED
} FrontendActionType;

typedef struct FrontendAction {
    FrontendActionType type;
    SongCatalogEntry song;
    u16 story_level;
    StoryDifficulty story_difficulty;
    u16 box_index;
} FrontendAction;

typedef struct Frontend {
    FrontendPage page;
    FrontendScreen screen;
    FrontendPlayer player;
    u8 main_selected;
    u8 character_selected;
    u8 extras_selected;
    u16 story_selected;
    StoryDifficulty story_difficulty;
    u16 pin_box_selected;
    u8 gammod_selected;
    u8 hud_selected;
    u8 option_selected;
    GammodConfig gammod_cache;
    boolean gammod_cache_loaded;
    boolean font_ready;
    GSFONTM *rom_font;
} Frontend;

void Frontend_Init(Frontend *frontend, GSFONTM *rom_font);
FrontendAction Frontend_Update(
    Frontend *frontend,
    FreeplayBrowser *freeplay,
    const SongCatalog *songs,
    const StoryCatalog *story,
    const ProgressionState *progression,
    const PointlessPinsCatalog *pins,
    FunkinSaveData *save,
    const Pad *pad);
void Frontend_Draw(
    GSGLOBAL *gs,
    Frontend *frontend,
    const FreeplayBrowser *freeplay,
    const SongCatalog *songs,
    const StoryCatalog *story,
    const ProgressionState *progression,
    const PointlessPinsCatalog *pins,
    const FunkinSaveData *save,
    BetterAlphabet *alphabet);
boolean Frontend_PicoSelected(const Frontend *frontend);

#endif
