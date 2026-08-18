#include "freeplay_browser.h"

#include <stdio.h>
#include <string.h>

#define BROWSER_ROWS 11u
#define BROWSER_PAGE_JUMP 10u

static void browser_keep_visible(FreeplayBrowser *browser, const SongCatalog *catalog)
{
    if (browser == NULL || catalog == NULL || catalog->count == 0)
        return;

    if (browser->selected >= catalog->count)
        browser->selected = catalog->count - 1;

    if (browser->selected < browser->first_visible)
        browser->first_visible = browser->selected;
    if (browser->selected >= browser->first_visible + browser->visible_rows)
        browser->first_visible = browser->selected - browser->visible_rows + 1;
}

boolean FreeplayBrowser_InitFont(GSGLOBAL *gs, FreeplayBrowser *browser)
{
    if (gs == NULL || browser == NULL)
        return false;

    memset(browser, 0, sizeof(*browser));
    browser->visible_rows = BROWSER_ROWS;
    browser->font = gsKit_init_fontm();
    if (browser->font == NULL)
        return false;

    if (gsKit_fontm_upload(gs, browser->font) < 0) {
        gsKit_free_fontm(gs, browser->font);
        browser->font = NULL;
        browser->font_ready = false;
        return false;
    }

    browser->font->Spacing = 0.90f;
    browser->font->Align = GSKIT_FALIGN_LEFT;
    browser->font_ready = true;
    return true;
}

void FreeplayBrowser_Reset(FreeplayBrowser *browser)
{
    if (browser == NULL)
        return;
    browser->selected = 0;
    browser->first_visible = 0;
    if (browser->visible_rows == 0)
        browser->visible_rows = BROWSER_ROWS;
}

void FreeplayBrowser_Update(
    FreeplayBrowser *browser,
    const SongCatalog *catalog,
    const Pad *pad)
{
    if (browser == NULL || catalog == NULL || pad == NULL || catalog->count == 0)
        return;

    if (pad->press & PAD_UP) {
        if (browser->selected == 0)
            browser->selected = catalog->count - 1;
        else
            --browser->selected;
    }
    if (pad->press & PAD_DOWN) {
        ++browser->selected;
        if (browser->selected >= catalog->count)
            browser->selected = 0;
    }
    if (pad->press & PAD_L1) {
        if (browser->selected > BROWSER_PAGE_JUMP)
            browser->selected -= BROWSER_PAGE_JUMP;
        else
            browser->selected = 0;
    }
    if (pad->press & PAD_R1) {
        browser->selected += BROWSER_PAGE_JUMP;
        if (browser->selected >= catalog->count)
            browser->selected = catalog->count - 1;
    }

    browser_keep_visible(browser, catalog);
}

boolean FreeplayBrowser_Selected(
    const FreeplayBrowser *browser,
    const SongCatalog *catalog,
    SongCatalogEntry *entry)
{
    if (browser == NULL || catalog == NULL || entry == NULL)
        return false;
    return SongCatalog_Get(catalog, browser->selected, entry);
}

void FreeplayBrowser_Draw(
    GSGLOBAL *gs,
    const FreeplayBrowser *browser,
    const SongCatalog *catalog)
{
    const u64 black = GS_SETREG_RGBAQ(0x00, 0x00, 0x00, 0x80, 0x00);
    const u64 background = GS_SETREG_RGBAQ(0x18, 0x14, 0x28, 0x80, 0x00);
    const u64 panel = GS_SETREG_RGBAQ(0x28, 0x22, 0x38, 0x80, 0x00);
    const u64 highlight = GS_SETREG_RGBAQ(0x70, 0x38, 0x80, 0x80, 0x00);
    const u64 white = GS_SETREG_RGBAQ(0x80, 0x80, 0x80, 0x80, 0x00);
    const u64 dim = GS_SETREG_RGBAQ(0x58, 0x58, 0x68, 0x80, 0x00);
    const u64 accent = GS_SETREG_RGBAQ(0x80, 0x60, 0x80, 0x80, 0x00);
    u32 row;
    char line[256];

    if (gs == NULL)
        return;

    gsKit_clear(gs, black);
    gsKit_prim_sprite(gs, 0.0f, 44.0f, 640.0f, 404.0f, 1, background);
    gsKit_prim_sprite(gs, 28.0f, 66.0f, 612.0f, 382.0f, 2, panel);

    if (browser == NULL || catalog == NULL || !catalog->loaded || catalog->count == 0) {
        if (browser != NULL && browser->font_ready) {
            gsKit_fontm_print_scaled(
                gs, browser->font, 64.0f, 188.0f, 4, 0.55f, white,
                "NO SONG CATALOG FOUND");
        }
        return;
    }

    if (browser->font_ready) {
        snprintf(line, sizeof(line), "FREEPLAY  %u CHARTS", (unsigned)catalog->count);
        gsKit_fontm_print_scaled(gs, browser->font, 52.0f, 78.0f, 4, 0.58f, accent, line);

        for (row = 0; row < browser->visible_rows; ++row) {
            u32 index = browser->first_visible + row;
            SongCatalogEntry entry;
            float y = 112.0f + (float)row * 21.0f;
            u64 color = dim;

            if (index >= catalog->count)
                break;
            if (!SongCatalog_Get(catalog, index, &entry))
                continue;

            if (index == browser->selected) {
                gsKit_prim_sprite(gs, 44.0f, y - 3.0f, 596.0f, y + 17.0f, 3, highlight);
                color = white;
            }

            if (strcmp(entry.variation, "default") == 0) {
                snprintf(line, sizeof(line), "%s  [%s]",
                    entry.display_name, entry.difficulty);
            } else {
                snprintf(line, sizeof(line), "%s / %s  [%s]",
                    entry.display_name, entry.variation, entry.difficulty);
            }
            gsKit_fontm_print_scaled(gs, browser->font, 56.0f, y, 4, 0.43f, color, line);
        }

        snprintf(line, sizeof(line), "%u / %u   X PLAY   L1/R1 PAGE   SELECT TV MODE",
            (unsigned)(browser->selected + 1), (unsigned)catalog->count);
        gsKit_fontm_print_scaled(gs, browser->font, 52.0f, 354.0f, 4, 0.38f, dim, line);
    }
}
