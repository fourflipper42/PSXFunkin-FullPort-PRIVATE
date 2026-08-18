#ifndef FNF_PS2_FRONTEND_H
#define FNF_PS2_FRONTEND_H

#include "better_alphabet.h"
#include "freeplay_browser.h"
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
    FRONTEND_OPTIONS,
    FRONTEND_PAGE_COUNT
} FrontendPage;

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
    FrontendPlayer player;
    u16 story_selected;
    StoryDifficulty story_difficulty;
    u16 pin_box_selected;
    u8 option_selected;
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
