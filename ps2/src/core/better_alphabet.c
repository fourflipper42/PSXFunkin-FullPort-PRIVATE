#include "better_alphabet.h"

#include "asset_file.h"
#include "mem.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct BetterAlphabetHeader {
    char magic[4];
    u16 version;
    u16 block_count;
    u32 glyph_count;
    u32 string_bytes;
    u32 block_size;
    u32 glyph_size;
    s32 height;
    s32 height_bold;
    s32 width;
    s32 width_bold;
    s32 padding;
    s32 padding_bold;
    s32 line_height;
    s32 space_width;
    u32 flags;
} __attribute__((packed)) BetterAlphabetHeader;

#define BALPH_VERSION 1
#define BALPH_NO_FRAME 0xFFFFu
#define BALPH_FLAG_ANTIALIAS (1u << 0)
#define BALPH_GLYPH_MONO_OVERRIDE (1u << 0)
#define BALPH_GLYPH_MONO_VALUE    (1u << 1)

static const char *font_string(const BetterAlphabet *font, u32 offset)
{
    const char *value;
    size_t left;
    if (font == NULL || font->strings == NULL || offset >= font->string_bytes)
        return NULL;
    value = font->strings + offset;
    left = font->string_bytes - offset;
    return memchr(value, '\0', left) != NULL ? value : NULL;
}

static void uppercase(char *text)
{
    if (text == NULL)
        return;
    while (*text != '\0') {
        *text = (char)toupper((unsigned char)*text);
        ++text;
    }
}

static boolean build_path(
    char *out,
    size_t out_size,
    const char *base,
    const char *style,
    const char *block,
    const char *leaf)
{
    int wrote;
    boolean disc;
    if (out == NULL || out_size == 0 || base == NULL || leaf == NULL)
        return false;
    disc = base[0] == '\\' || strncmp(base, "cdrom0:", 7) == 0;
    if (style != NULL && block != NULL) {
        wrote = snprintf(out, out_size, "%s%c%s%c%s%c%s%s",
            base, disc ? '\\' : '/', style, disc ? '\\' : '/', block,
            disc ? '\\' : '/', leaf, disc ? ";1" : "");
    } else {
        wrote = snprintf(out, out_size, "%s%c%s%s",
            base, disc ? '\\' : '/', leaf, disc ? ";1" : "");
    }
    if (wrote < 0 || (size_t)wrote >= out_size)
        return false;
    if (disc)
        uppercase(out);
    return true;
}

boolean BetterAlphabet_Load(GSGLOBAL *gs, BetterAlphabet *font, const char *base_path)
{
    AssetFile file;
    BetterAlphabetHeader *header;
    size_t blocks_bytes;
    size_t glyphs_bytes;
    size_t minimum;
    size_t got;
    u8 *cursor;
    u16 i;
    char catalog[320];

    if (font == NULL || base_path == NULL)
        return false;
    memset(font, 0, sizeof(*font));
    memset(&file, 0, sizeof(file));
    strncpy(font->base_path, base_path, sizeof(font->base_path) - 1);

    if (!build_path(catalog, sizeof(catalog), base_path, NULL, NULL, "FONT.FBAL") ||
        !AssetFile_Open(&file, catalog))
        return false;
    font->catalog_size = AssetFile_Size(&file);
    if (font->catalog_size < sizeof(BetterAlphabetHeader))
        goto fail;
    font->catalog_blob = Mem_Alloc(font->catalog_size);
    if (font->catalog_blob == NULL)
        goto fail;
    got = AssetFile_Read(&file, font->catalog_blob, font->catalog_size);
    AssetFile_Close(&file);
    if (got != font->catalog_size)
        goto fail;

    header = (BetterAlphabetHeader *)font->catalog_blob;
    if (memcmp(header->magic, "FBAL", 4) != 0 ||
        header->version != BALPH_VERSION ||
        header->block_size != sizeof(BetterAlphabetBlockRecord) ||
        header->glyph_size != sizeof(BetterAlphabetGlyphRecord))
        goto fail;
    blocks_bytes = (size_t)header->block_count * sizeof(BetterAlphabetBlockRecord);
    glyphs_bytes = (size_t)header->glyph_count * sizeof(BetterAlphabetGlyphRecord);
    minimum = sizeof(BetterAlphabetHeader) + blocks_bytes + glyphs_bytes + header->string_bytes;
    if (minimum > font->catalog_size)
        goto fail;

    cursor = (u8 *)font->catalog_blob + sizeof(BetterAlphabetHeader);
    font->blocks = (BetterAlphabetBlockRecord *)cursor;
    cursor += blocks_bytes;
    font->glyphs = (BetterAlphabetGlyphRecord *)cursor;
    cursor += glyphs_bytes;
    font->strings = (char *)cursor;
    font->block_count = header->block_count;
    font->glyph_count = header->glyph_count;
    font->string_bytes = header->string_bytes;
    font->height = header->height;
    font->height_bold = header->height_bold;
    font->width = header->width;
    font->width_bold = header->width_bold;
    font->padding = header->padding;
    font->padding_bold = header->padding_bold;
    font->line_height = header->line_height;
    font->space_width = header->space_width;
    font->flags = header->flags;

    for (i = 0; i < font->block_count; ++i) {
        if (font_string(font, font->blocks[i].name_offset) == NULL)
            goto fail;
    }
    for (i = 0; i < font->glyph_count; ++i) {
        if (font->glyphs[i].block_index >= font->block_count)
            goto fail;
        if (i != 0 && font->glyphs[i - 1].codepoint >= font->glyphs[i].codepoint)
            goto fail;
    }

    if (font->block_count != 0) {
        font->regular = (SpriteAtlas *)Mem_Alloc(sizeof(SpriteAtlas) * font->block_count);
        font->bold = (SpriteAtlas *)Mem_Alloc(sizeof(SpriteAtlas) * font->block_count);
        if (font->regular == NULL || font->bold == NULL)
            goto fail;
        memset(font->regular, 0, sizeof(SpriteAtlas) * font->block_count);
        memset(font->bold, 0, sizeof(SpriteAtlas) * font->block_count);

        for (i = 0; i < font->block_count; ++i) {
            const char *block = font_string(font, font->blocks[i].name_offset);
            char texture[320];
            char frames[320];
            if (build_path(texture, sizeof(texture), base_path, "REGULAR", block, "GLYPH.FPTX") &&
                build_path(frames, sizeof(frames), base_path, "REGULAR", block, "GLYPH.FATL"))
                SpriteAtlas_Load(gs, &font->regular[i], texture, frames,
                    (font->flags & BALPH_FLAG_ANTIALIAS) != 0);
            if (build_path(texture, sizeof(texture), base_path, "BOLD", block, "GLYPH.FPTX") &&
                build_path(frames, sizeof(frames), base_path, "BOLD", block, "GLYPH.FATL"))
                SpriteAtlas_Load(gs, &font->bold[i], texture, frames,
                    (font->flags & BALPH_FLAG_ANTIALIAS) != 0);
        }
    }

    font->loaded = true;
    return true;

fail:
    AssetFile_Close(&file);
    BetterAlphabet_Forget(font);
    return false;
}

void BetterAlphabet_Forget(BetterAlphabet *font)
{
    u16 i;
    if (font == NULL)
        return;
    if (font->regular != NULL) {
        for (i = 0; i < font->block_count; ++i)
            if (font->regular[i].loaded) SpriteAtlas_Forget(&font->regular[i]);
        Mem_Free(font->regular);
    }
    if (font->bold != NULL) {
        for (i = 0; i < font->block_count; ++i)
            if (font->bold[i].loaded) SpriteAtlas_Forget(&font->bold[i]);
        Mem_Free(font->bold);
    }
    if (font->catalog_blob != NULL)
        Mem_Free(font->catalog_blob);
    memset(font, 0, sizeof(*font));
}

static const BetterAlphabetGlyphRecord *find_glyph(const BetterAlphabet *font, u32 codepoint)
{
    u32 lo = 0;
    u32 hi;
    if (font == NULL || !font->loaded || font->glyph_count == 0)
        return NULL;
    hi = font->glyph_count;
    while (lo < hi) {
        u32 mid = lo + (hi - lo) / 2;
        u32 value = font->glyphs[mid].codepoint;
        if (value == codepoint)
            return &font->glyphs[mid];
        if (value < codepoint)
            lo = mid + 1;
        else
            hi = mid;
    }
    return NULL;
}

static u32 decode_utf8(const char **cursor)
{
    const unsigned char *s = (const unsigned char *)*cursor;
    u32 cp;
    if (*s < 0x80) {
        *cursor += 1;
        return *s;
    }
    if ((*s & 0xE0) == 0xC0 && (s[1] & 0xC0) == 0x80) {
        cp = ((u32)(s[0] & 0x1F) << 6) | (s[1] & 0x3F);
        *cursor += 2;
        return cp;
    }
    if ((*s & 0xF0) == 0xE0 && (s[1] & 0xC0) == 0x80 && (s[2] & 0xC0) == 0x80) {
        cp = ((u32)(s[0] & 0x0F) << 12) | ((u32)(s[1] & 0x3F) << 6) | (s[2] & 0x3F);
        *cursor += 3;
        return cp;
    }
    if ((*s & 0xF8) == 0xF0 && (s[1] & 0xC0) == 0x80 &&
        (s[2] & 0xC0) == 0x80 && (s[3] & 0xC0) == 0x80) {
        cp = ((u32)(s[0] & 0x07) << 18) | ((u32)(s[1] & 0x3F) << 12) |
            ((u32)(s[2] & 0x3F) << 6) | (s[3] & 0x3F);
        *cursor += 4;
        return cp;
    }
    *cursor += 1;
    return 0xFFFDu;
}

static boolean parse_entity(const char **cursor, u32 *codepoint)
{
    const char *s = *cursor;
    const char *end;
    char number[16];
    size_t n;
    int base = 10;
    unsigned long value;
    char *tail;
    if (s[0] != '&' || s[1] != '#')
        return false;
    s += 2;
    if (*s == 'x' || *s == 'X') {
        base = 16;
        ++s;
    }
    end = strchr(s, ';');
    if (end == NULL)
        return false;
    n = (size_t)(end - s);
    if (n == 0 || n >= sizeof(number))
        return false;
    memcpy(number, s, n);
    number[n] = '\0';
    value = strtoul(number, &tail, base);
    if (*tail != '\0' || value > 0x10FFFFul)
        return false;
    *codepoint = (u32)value;
    *cursor = end + 1;
    return true;
}

typedef struct TextStyle {
    boolean bold;
    float scale;
    u8 r;
    u8 g;
    u8 b;
} TextStyle;

static boolean starts(const char *s, const char *prefix)
{
    return s != NULL && prefix != NULL && strncmp(s, prefix, strlen(prefix)) == 0;
}

static boolean parse_hex_color(const char *s, u8 *r, u8 *g, u8 *b)
{
    char hex[7];
    char *end;
    unsigned long value;
    int i;
    for (i = 0; i < 6; ++i) {
        if (!isxdigit((unsigned char)s[i]))
            return false;
        hex[i] = s[i];
    }
    hex[6] = '\0';
    value = strtoul(hex, &end, 16);
    if (*end != '\0')
        return false;
    *r = (u8)((value >> 16) & 0xFFu);
    *g = (u8)((value >> 8) & 0xFFu);
    *b = (u8)(value & 0xFFu);
    return true;
}

static boolean consume_markup(const char **cursor, TextStyle *style)
{
    const char *s = *cursor;
    const char *end;
    if (*s != '<')
        return false;
    end = strchr(s, '>');
    if (end == NULL)
        return false;

    if (starts(s, "<b>"))
        style->bold = true;
    else if (starts(s, "</b>"))
        style->bold = false;
    else if (starts(s, "<c=") && end - s >= 9)
        parse_hex_color(s + 3, &style->r, &style->g, &style->b);
    else if (starts(s, "</c>"))
        style->r = style->g = style->b = 255;
    else if (starts(s, "<s=")) {
        char temp[24];
        size_t n = (size_t)(end - (s + 3));
        if (n < sizeof(temp)) {
            memcpy(temp, s + 3, n);
            temp[n] = '\0';
            style->scale = (float)atof(temp);
            if (style->scale <= 0.0f) style->scale = 1.0f;
        }
    } else if (starts(s, "</s>")) {
        style->scale = 1.0f;
    }
    /* Italic/alignment/delay/effect tags are intentionally consumed even when
     * the PS2 sprite path has no equivalent, preserving text instead of
     * rendering the literal markup. */
    *cursor = end + 1;
    return true;
}

static u64 glyph_color(const TextStyle *style)
{
    u8 r = (u8)(((u32)style->r * 0x80u + 127u) / 255u);
    u8 g = (u8)(((u32)style->g * 0x80u + 127u) / 255u);
    u8 b = (u8)(((u32)style->b * 0x80u + 127u) / 255u);
    return GS_SETREG_RGBAQ(r, g, b, 0x80, 0);
}

static float draw_or_measure(
    GSGLOBAL *gs,
    BetterAlphabet *font,
    float x,
    float y,
    float scale,
    int z,
    const char *text)
{
    const char *cursor = text;
    float start_x = x;
    float pos_x = x;
    float pos_y = y;
    float max_x = x;
    TextStyle style;

    if (font == NULL || !font->loaded || text == NULL)
        return 0.0f;
    style.bold = false;
    style.scale = 1.0f;
    style.r = style.g = style.b = 255;

    while (*cursor != '\0') {
        u32 cp;
        const BetterAlphabetGlyphRecord *glyph;
        SpriteAtlas *atlas;
        u16 frame_index;
        const AtlasFrame *frame;
        float local_scale;
        float advance;
        boolean mono;

        if (*cursor == '<' && consume_markup(&cursor, &style))
            continue;
        if (*cursor == '&' && parse_entity(&cursor, &cp)) {
            /* decoded below */
        } else {
            cp = decode_utf8(&cursor);
        }

        if (cp == '\r')
            continue;
        if (cp == '\n') {
            if (pos_x > max_x) max_x = pos_x;
            pos_x = start_x;
            pos_y += (float)font->line_height * scale * 0.5f * style.scale;
            continue;
        }
        if (cp == ' ') {
            pos_x += (float)font->space_width * scale * 0.5f * style.scale;
            continue;
        }

        glyph = find_glyph(font, cp);
        if (glyph == NULL)
            glyph = find_glyph(font, '?');
        if (glyph == NULL || glyph->block_index >= font->block_count)
            continue;

        atlas = style.bold ? &font->bold[glyph->block_index] : &font->regular[glyph->block_index];
        frame_index = style.bold ? glyph->bold_frame : glyph->regular_frame;
        if ((!atlas->loaded || frame_index == BALPH_NO_FRAME) && style.bold) {
            atlas = &font->regular[glyph->block_index];
            frame_index = glyph->regular_frame;
        }
        if (!atlas->loaded || frame_index == BALPH_NO_FRAME || frame_index >= atlas->frame_count)
            continue;
        frame = &atlas->frames[frame_index];
        local_scale = scale * 0.5f * style.scale;

        if (gs != NULL) {
            float draw_x = pos_x + (float)glyph->offset_x * local_scale;
            float letter_height = (float)(style.bold ? font->height_bold : font->height);
            float draw_y = pos_y + (letter_height - (float)frame->frame_height) * local_scale +
                (float)glyph->offset_y * local_scale;
            SpriteAtlas_DrawFrameEx(
                gs, atlas, frame_index,
                draw_x, draw_y,
                local_scale, local_scale,
                false, false, z, glyph_color(&style));
        }

        mono = (glyph->flags & BALPH_GLYPH_MONO_OVERRIDE)
            ? (glyph->flags & BALPH_GLYPH_MONO_VALUE) != 0
            : false;
        if (mono) {
            s32 width = style.bold ? font->width_bold : font->width;
            if (style.bold && width == 0) width = font->width;
            advance = (float)width * local_scale;
        } else {
            s32 padding = style.bold ? font->padding_bold : font->padding;
            advance = ((float)frame->frame_width + (float)padding + (float)glyph->offset_x) * local_scale;
        }
        pos_x += advance;
        if (pos_x > max_x) max_x = pos_x;
    }

    return max_x - start_x;
}

float BetterAlphabet_Draw(
    GSGLOBAL *gs,
    BetterAlphabet *font,
    float x,
    float y,
    float scale,
    int z,
    const char *text)
{
    return draw_or_measure(gs, font, x, y, scale, z, text);
}

float BetterAlphabet_Measure(BetterAlphabet *font, float scale, const char *text)
{
    return draw_or_measure(NULL, font, 0.0f, 0.0f, scale, 0, text);
}
