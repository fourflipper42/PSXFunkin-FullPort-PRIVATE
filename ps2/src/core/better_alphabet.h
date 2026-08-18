#ifndef FNF_PS2_BETTER_ALPHABET_H
#define FNF_PS2_BETTER_ALPHABET_H

#include "fixed.h"
#include "sprite_atlas.h"
#include <stddef.h>

typedef struct BetterAlphabetBlockRecord {
    u32 name_offset;
} __attribute__((packed)) BetterAlphabetBlockRecord;

typedef struct BetterAlphabetGlyphRecord {
    u32 codepoint;
    s16 offset_x;
    s16 offset_y;
    u16 block_index;
    u16 regular_frame;
    u16 bold_frame;
    u16 flags;
} __attribute__((packed)) BetterAlphabetGlyphRecord;

typedef struct BetterAlphabet {
    void *catalog_blob;
    size_t catalog_size;
    BetterAlphabetBlockRecord *blocks;
    BetterAlphabetGlyphRecord *glyphs;
    char *strings;
    SpriteAtlas *regular;
    SpriteAtlas *bold;
    u16 block_count;
    u32 glyph_count;
    u32 string_bytes;
    s32 height;
    s32 height_bold;
    s32 width;
    s32 width_bold;
    s32 padding;
    s32 padding_bold;
    s32 line_height;
    s32 space_width;
    u32 flags;
    boolean loaded;
    char base_path[256];
} BetterAlphabet;

boolean BetterAlphabet_Load(GSGLOBAL *gs, BetterAlphabet *font, const char *base_path);
void BetterAlphabet_Forget(BetterAlphabet *font);
float BetterAlphabet_Draw(
    GSGLOBAL *gs,
    BetterAlphabet *font,
    float x,
    float y,
    float scale,
    int z,
    const char *text);
float BetterAlphabet_Measure(BetterAlphabet *font, float scale, const char *text);

#endif
