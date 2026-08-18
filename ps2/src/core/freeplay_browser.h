#ifndef FNF_PS2_FREEPLAY_BROWSER_H
#define FNF_PS2_FREEPLAY_BROWSER_H

#include "pad.h"
#include "song_catalog.h"
#include <gsKit.h>
#include <gsToolkit.h>

typedef struct FreeplayBrowser {
    GSFONTM *font;
    u32 selected;
    u32 first_visible;
    u32 visible_rows;
    boolean font_ready;
} FreeplayBrowser;

boolean FreeplayBrowser_InitFont(GSGLOBAL *gs, FreeplayBrowser *browser);
void FreeplayBrowser_Reset(FreeplayBrowser *browser);
void FreeplayBrowser_Update(
    FreeplayBrowser *browser,
    const SongCatalog *catalog,
    const Pad *pad);
boolean FreeplayBrowser_Selected(
    const FreeplayBrowser *browser,
    const SongCatalog *catalog,
    SongCatalogEntry *entry);
void FreeplayBrowser_Draw(
    GSGLOBAL *gs,
    const FreeplayBrowser *browser,
    const SongCatalog *catalog);

#endif
