#include "frontend.h"

#include "ps2_glyph.h"
#include <string.h>

void Frontend_InitCore(Frontend *frontend, GSFONTM *rom_font);
FrontendAction Frontend_UpdateCore(
    Frontend *frontend,
    FreeplayBrowser *freeplay,
    const SongCatalog *songs,
    const StoryCatalog *story,
    const ProgressionState *progression,
    const PointlessPinsCatalog *pins,
    FunkinSaveData *save,
    const Pad *pad);
void Frontend_DrawCore(
    GSGLOBAL *gs,
    Frontend *frontend,
    const FreeplayBrowser *freeplay,
    const SongCatalog *songs,
    const StoryCatalog *story,
    const ProgressionState *progression,
    const PointlessPinsCatalog *pins,
    const FunkinSaveData *save,
    BetterAlphabet *alphabet);

static const char *const main_items[FRONTEND_MAIN_COUNT] = {
    "STORY MODE",
    "FREEPLAY",
    "CHARACTER SELECT",
    "OPTIONS",
    "EXTRAS"
};

static const char *const extra_items[FRONTEND_EXTRA_COUNT] = {
    "GAMMOD",
    "CUSTOM HUD",
    "POINTLESS PINS"
};

static u64 white(void) { return GS_SETREG_RGBAQ(0x80, 0x80, 0x80, 0x80, 0); }
static u64 dim(void) { return GS_SETREG_RGBAQ(0x50, 0x50, 0x60, 0x80, 0); }
static u64 accent(void) { return GS_SETREG_RGBAQ(0x80, 0x58, 0x78, 0x80, 0); }
static u64 panel(void) { return GS_SETREG_RGBAQ(0x24, 0x20, 0x34, 0x80, 0); }
static u64 select_color(void) { return GS_SETREG_RGBAQ(0x58, 0x30, 0x68, 0x80, 0); }
static u64 locked_color(void) { return GS_SETREG_RGBAQ(0x48, 0x38, 0x3c, 0x80, 0); }

static void shell_text(
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
    if (text == NULL)
        return;
    if (alphabet != NULL && alphabet->loaded) {
        (void)color;
        BetterAlphabet_Draw(gs, alphabet, x, y, scale * 1.1f, z, text);
    } else if (frontend != NULL && frontend->font_ready && frontend->rom_font != NULL) {
        gsKit_fontm_print_scaled(gs, frontend->rom_font, x, y, z, scale, color, text);
    }
}

static void wrap_selection(u8 *selected, u8 count, int direction)
{
    int value;
    if (selected == NULL || count == 0 || direction == 0)
        return;
    value = (int)*selected + direction;
    while (value < 0) value += count;
    while (value >= count) value -= count;
    *selected = (u8)value;
}

static boolean pico_available(
    const ProgressionState *progression,
    const StoryCatalog *story)
{
    return Progression_PicoUnlocked(progression, story);
}

static void open_page(Frontend *frontend, FrontendPage page)
{
    if (frontend == NULL)
        return;
    frontend->page = page;
    frontend->screen = FRONTEND_SCREEN_PAGE;
}

void Frontend_Init(Frontend *frontend, GSFONTM *rom_font)
{
    Frontend_InitCore(frontend, rom_font);
    if (frontend == NULL)
        return;
    frontend->screen = FRONTEND_SCREEN_TITLE;
    frontend->main_selected = FRONTEND_MAIN_STORY;
    frontend->character_selected = (u8)frontend->player;
    frontend->extras_selected = FRONTEND_EXTRA_GAMMOD;
}

static FrontendAction update_title(Frontend *frontend, const Pad *pad)
{
    FrontendAction action;
    memset(&action, 0, sizeof(action));
    if (pad->press & (PAD_START | PAD_CROSS))
        frontend->screen = FRONTEND_SCREEN_MAIN;
    return action;
}

static FrontendAction update_main(Frontend *frontend, const Pad *pad)
{
    FrontendAction action;
    memset(&action, 0, sizeof(action));

    if (pad->press & PAD_UP)
        wrap_selection(&frontend->main_selected, FRONTEND_MAIN_COUNT, -1);
    if (pad->press & PAD_DOWN)
        wrap_selection(&frontend->main_selected, FRONTEND_MAIN_COUNT, 1);
    if (!(pad->press & PAD_CROSS))
        return action;

    switch ((FrontendMainItem)frontend->main_selected) {
        case FRONTEND_MAIN_STORY:
            open_page(frontend, FRONTEND_STORY);
            break;
        case FRONTEND_MAIN_FREEPLAY:
            open_page(frontend, FRONTEND_FREEPLAY);
            break;
        case FRONTEND_MAIN_CHARACTER:
            frontend->character_selected = (u8)frontend->player;
            frontend->screen = FRONTEND_SCREEN_CHARACTER;
            break;
        case FRONTEND_MAIN_OPTIONS:
            open_page(frontend, FRONTEND_OPTIONS);
            break;
        case FRONTEND_MAIN_EXTRAS:
            frontend->screen = FRONTEND_SCREEN_EXTRAS;
            break;
        default:
            break;
    }
    return action;
}

static FrontendAction update_character(
    Frontend *frontend,
    const StoryCatalog *story,
    const ProgressionState *progression,
    const Pad *pad)
{
    FrontendAction action;
    memset(&action, 0, sizeof(action));

    if (pad->press & (PAD_LEFT | PAD_UP))
        wrap_selection(&frontend->character_selected, 2, -1);
    if (pad->press & (PAD_RIGHT | PAD_DOWN))
        wrap_selection(&frontend->character_selected, 2, 1);
    if (pad->press & PAD_CIRCLE) {
        frontend->character_selected = (u8)frontend->player;
        frontend->screen = FRONTEND_SCREEN_MAIN;
        return action;
    }
    if (pad->press & PAD_CROSS) {
        if (frontend->character_selected == FRONTEND_PLAYER_BF ||
            pico_available(progression, story)) {
            frontend->player = (FrontendPlayer)frontend->character_selected;
            frontend->screen = FRONTEND_SCREEN_MAIN;
        }
    }
    return action;
}

static FrontendAction update_extras(Frontend *frontend, const Pad *pad)
{
    FrontendAction action;
    memset(&action, 0, sizeof(action));

    if (pad->press & PAD_UP)
        wrap_selection(&frontend->extras_selected, FRONTEND_EXTRA_COUNT, -1);
    if (pad->press & PAD_DOWN)
        wrap_selection(&frontend->extras_selected, FRONTEND_EXTRA_COUNT, 1);
    if (pad->press & PAD_CIRCLE) {
        frontend->screen = FRONTEND_SCREEN_MAIN;
        return action;
    }
    if (!(pad->press & PAD_CROSS))
        return action;

    switch ((FrontendExtraItem)frontend->extras_selected) {
        case FRONTEND_EXTRA_GAMMOD: open_page(frontend, FRONTEND_GAMMOD); break;
        case FRONTEND_EXTRA_HUD: open_page(frontend, FRONTEND_HUD); break;
        case FRONTEND_EXTRA_PINS: open_page(frontend, FRONTEND_PINS); break;
        default: break;
    }
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
    Pad filtered;
    memset(&action, 0, sizeof(action));
    if (frontend == NULL || pad == NULL)
        return action;

    switch (frontend->screen) {
        case FRONTEND_SCREEN_TITLE:
            return update_title(frontend, pad);
        case FRONTEND_SCREEN_MAIN:
            return update_main(frontend, pad);
        case FRONTEND_SCREEN_CHARACTER:
            return update_character(frontend, story, progression, pad);
        case FRONTEND_SCREEN_EXTRAS:
            return update_extras(frontend, pad);
        case FRONTEND_SCREEN_PAGE:
        default:
            break;
    }

    if (pad->press & PAD_CIRCLE) {
        if (frontend->page == FRONTEND_GAMMOD ||
            frontend->page == FRONTEND_HUD ||
            frontend->page == FRONTEND_PINS)
            frontend->screen = FRONTEND_SCREEN_EXTRAS;
        else
            frontend->screen = FRONTEND_SCREEN_MAIN;
        return action;
    }

    filtered = *pad;
    filtered.press &= (u16)~(PAD_L2 | PAD_R2 | PAD_CIRCLE);
    filtered.held &= (u16)~(PAD_L2 | PAD_R2 | PAD_CIRCLE);
    return Frontend_UpdateCore(
        frontend,
        freeplay,
        songs,
        story,
        progression,
        pins,
        save,
        &filtered);
}

static void clear_shell(GSGLOBAL *gs)
{
    const u64 black = GS_SETREG_RGBAQ(0x00, 0x00, 0x00, 0x80, 0);
    const u64 bg = GS_SETREG_RGBAQ(0x18, 0x14, 0x28, 0x80, 0);
    gsKit_clear(gs, black);
    gsKit_prim_sprite(gs, 0.0f, 44.0f, 640.0f, 404.0f, 1, bg);
}

static void draw_title(GSGLOBAL *gs, Frontend *frontend, BetterAlphabet *alphabet)
{
    clear_shell(gs);
    gsKit_prim_sprite(gs, 68.0f, 106.0f, 572.0f, 330.0f, 2, panel());
    shell_text(gs, frontend, alphabet, 158.0f, 150.0f, 0.90f, 5, white(), "FRIDAY NIGHT");
    shell_text(gs, frontend, alphabet, 190.0f, 205.0f, 1.05f, 5, accent(), "FUNKIN'");
    shell_text(gs, frontend, alphabet, 221.0f, 278.0f, 0.43f, 5, white(), "PRESS START");
    Ps2Glyph_Draw(gs, PS2_GLYPH_CROSS, 300.0f, 322.0f, 20.0f, 7);
}

static void draw_main(GSGLOBAL *gs, Frontend *frontend, BetterAlphabet *alphabet)
{
    u8 i;
    clear_shell(gs);
    shell_text(gs, frontend, alphabet, 48.0f, 74.0f, 0.64f, 5, accent(), "FRIDAY NIGHT FUNKIN'");
    for (i = 0; i < FRONTEND_MAIN_COUNT; ++i) {
        float y = 132.0f + i * 49.0f;
        if (i == frontend->main_selected)
            gsKit_prim_sprite(gs, 126.0f, y - 8.0f, 514.0f, y + 29.0f, 2, select_color());
        shell_text(gs, frontend, alphabet, 158.0f, y, 0.54f, 5, white(), main_items[i]);
    }
    Ps2Glyph_Draw(gs, PS2_GLYPH_CROSS, 548.0f, 405.0f, 18.0f, 8);
    shell_text(gs, frontend, alphabet, 570.0f, 407.0f, 0.25f, 8, dim(), "SELECT");
}

static void draw_character(
    GSGLOBAL *gs,
    Frontend *frontend,
    const StoryCatalog *story,
    const ProgressionState *progression,
    BetterAlphabet *alphabet)
{
    boolean pico = pico_available(progression, story);
    u64 bf_color = frontend->character_selected == FRONTEND_PLAYER_BF ? select_color() : panel();
    u64 pico_color = frontend->character_selected == FRONTEND_PLAYER_PICO ? select_color() : panel();

    clear_shell(gs);
    shell_text(gs, frontend, alphabet, 160.0f, 76.0f, 0.68f, 5, accent(), "CHARACTER SELECT");
    gsKit_prim_sprite(gs, 66.0f, 142.0f, 300.0f, 330.0f, 2, bf_color);
    gsKit_prim_sprite(gs, 340.0f, 142.0f, 574.0f, 330.0f, 2,
        pico ? pico_color : locked_color());
    shell_text(gs, frontend, alphabet, 112.0f, 218.0f, 0.62f, 5, white(), "BOYFRIEND");
    shell_text(gs, frontend, alphabet, 419.0f, 218.0f, 0.62f, 5,
        pico ? white() : dim(), "PICO");
    if (!pico)
        shell_text(gs, frontend, alphabet, 359.0f, 274.0f, 0.30f, 5, dim(), "CLEAR WEEKEND 1 TO UNLOCK");
    shell_text(gs, frontend, alphabet, 82.0f, 366.0f, 0.31f, 5, dim(), "LEFT/RIGHT SELECT");
    Ps2Glyph_Draw(gs, PS2_GLYPH_CIRCLE, 418.0f, 402.0f, 18.0f, 8);
    shell_text(gs, frontend, alphabet, 441.0f, 405.0f, 0.25f, 8, dim(), "BACK");
    Ps2Glyph_Draw(gs, PS2_GLYPH_CROSS, 526.0f, 402.0f, 18.0f, 8);
    shell_text(gs, frontend, alphabet, 549.0f, 405.0f, 0.25f, 8, dim(), "SELECT");
}

static void draw_extras(GSGLOBAL *gs, Frontend *frontend, BetterAlphabet *alphabet)
{
    u8 i;
    clear_shell(gs);
    shell_text(gs, frontend, alphabet, 240.0f, 80.0f, 0.68f, 5, accent(), "EXTRAS");
    for (i = 0; i < FRONTEND_EXTRA_COUNT; ++i) {
        float y = 160.0f + i * 58.0f;
        if (i == frontend->extras_selected)
            gsKit_prim_sprite(gs, 136.0f, y - 8.0f, 504.0f, y + 31.0f, 2, select_color());
        shell_text(gs, frontend, alphabet, 170.0f, y, 0.55f, 5, white(), extra_items[i]);
    }
    Ps2Glyph_Draw(gs, PS2_GLYPH_CIRCLE, 418.0f, 402.0f, 18.0f, 8);
    shell_text(gs, frontend, alphabet, 441.0f, 405.0f, 0.25f, 8, dim(), "BACK");
    Ps2Glyph_Draw(gs, PS2_GLYPH_CROSS, 526.0f, 402.0f, 18.0f, 8);
    shell_text(gs, frontend, alphabet, 549.0f, 405.0f, 0.25f, 8, dim(), "SELECT");
}

static void draw_page_footer(GSGLOBAL *gs, Frontend *frontend, BetterAlphabet *alphabet)
{
    const u64 footer = GS_SETREG_RGBAQ(0x18, 0x14, 0x28, 0x80, 0);
    gsKit_prim_sprite(gs, 0.0f, 398.0f, 126.0f, 448.0f, 30, footer);
    gsKit_prim_sprite(gs, 500.0f, 398.0f, 640.0f, 448.0f, 30, footer);
    Ps2Glyph_Draw(gs, PS2_GLYPH_CIRCLE, 508.0f, 405.0f, 18.0f, 31);
    shell_text(gs, frontend, alphabet, 531.0f, 407.0f, 0.25f, 31, dim(), "BACK");
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
    if (gs == NULL || frontend == NULL)
        return;

    switch (frontend->screen) {
        case FRONTEND_SCREEN_TITLE:
            draw_title(gs, frontend, alphabet);
            return;
        case FRONTEND_SCREEN_MAIN:
            draw_main(gs, frontend, alphabet);
            return;
        case FRONTEND_SCREEN_CHARACTER:
            draw_character(gs, frontend, story, progression, alphabet);
            return;
        case FRONTEND_SCREEN_EXTRAS:
            draw_extras(gs, frontend, alphabet);
            return;
        case FRONTEND_SCREEN_PAGE:
        default:
            break;
    }

    Frontend_DrawCore(
        gs,
        frontend,
        freeplay,
        songs,
        story,
        progression,
        pins,
        save,
        alphabet);
    draw_page_footer(gs, frontend, alphabet);
}
