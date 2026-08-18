#include "ps2_glyph.h"

#include <math.h>

#define GLYPH_PI 3.14159265358979323846f

static float g_x_scale = 1.0f;
static float g_y_scale = 1.0f;
static float g_x_offset = 0.0f;
static float g_y_offset = 0.0f;

static float gx(float x) { return g_x_offset + x * g_x_scale; }
static float gy(float y) { return g_y_offset + y * g_y_scale; }

static u64 glyph_color(Ps2Glyph glyph)
{
    switch (glyph) {
        case PS2_GLYPH_TRIANGLE:
            return GS_SETREG_RGBAQ(0x35, 0xd9, 0x77, 0x80, 0x00);
        case PS2_GLYPH_CIRCLE:
            return GS_SETREG_RGBAQ(0xff, 0x5a, 0x6d, 0x80, 0x00);
        case PS2_GLYPH_CROSS:
            return GS_SETREG_RGBAQ(0x5d, 0xa9, 0xff, 0x80, 0x00);
        case PS2_GLYPH_SQUARE:
            return GS_SETREG_RGBAQ(0xe5, 0x75, 0xe8, 0x80, 0x00);
        default:
            return GS_SETREG_RGBAQ(0xee, 0xee, 0xee, 0x80, 0x00);
    }
}

static void line(
    GSGLOBAL *gs,
    float x1,
    float y1,
    float x2,
    float y2,
    int z,
    u64 color)
{
    gsKit_prim_line(gs, gx(x1), gy(y1), gx(x2), gy(y2), z, color);
}

static void thick_line(
    GSGLOBAL *gs,
    float x1,
    float y1,
    float x2,
    float y2,
    float thickness,
    int z,
    u64 color)
{
    float dx = x2 - x1;
    float dy = y2 - y1;
    float length = sqrtf(dx * dx + dy * dy);
    float nx;
    float ny;
    int i;
    int count;

    if (length <= 0.001f)
        return;
    nx = -dy / length;
    ny = dx / length;
    count = (int)(thickness + 0.5f);
    if (count < 1)
        count = 1;
    for (i = -count / 2; i <= count / 2; ++i) {
        float off = (float)i;
        line(gs, x1 + nx * off, y1 + ny * off,
            x2 + nx * off, y2 + ny * off, z, color);
    }
}

static void draw_circle(GSGLOBAL *gs, float x, float y, float size, int z, u64 color)
{
    int i;
    const int segments = 20;
    float cx = x + size * 0.5f;
    float cy = y + size * 0.5f;
    float radius = size * 0.38f;

    for (i = 0; i < segments; ++i) {
        float a = ((float)i / (float)segments) * GLYPH_PI * 2.0f;
        float b = ((float)(i + 1) / (float)segments) * GLYPH_PI * 2.0f;
        thick_line(gs,
            cx + cosf(a) * radius, cy + sinf(a) * radius,
            cx + cosf(b) * radius, cy + sinf(b) * radius,
            size * 0.08f, z, color);
    }
}

static void draw_face(GSGLOBAL *gs, Ps2Glyph glyph, float x, float y, float size, int z)
{
    u64 color = glyph_color(glyph);
    float p = size * 0.22f;
    float q = size - p;
    float t = size * 0.08f;

    switch (glyph) {
        case PS2_GLYPH_CROSS:
            thick_line(gs, x + p, y + p, x + q, y + q, t, z, color);
            thick_line(gs, x + q, y + p, x + p, y + q, t, z, color);
            break;
        case PS2_GLYPH_CIRCLE:
            draw_circle(gs, x, y, size, z, color);
            break;
        case PS2_GLYPH_SQUARE:
            thick_line(gs, x + p, y + p, x + q, y + p, t, z, color);
            thick_line(gs, x + q, y + p, x + q, y + q, t, z, color);
            thick_line(gs, x + q, y + q, x + p, y + q, t, z, color);
            thick_line(gs, x + p, y + q, x + p, y + p, t, z, color);
            break;
        case PS2_GLYPH_TRIANGLE:
            thick_line(gs, x + size * 0.5f, y + p,
                x + q, y + q, t, z, color);
            thick_line(gs, x + q, y + q,
                x + p, y + q, t, z, color);
            thick_line(gs, x + p, y + q,
                x + size * 0.5f, y + p, t, z, color);
            break;
        default:
            break;
    }
}

static void draw_label_box(GSGLOBAL *gs, Ps2Glyph glyph, float x, float y, float size, int z)
{
    const u64 color = glyph_color(glyph);
    float w = size * 1.35f;
    float h = size * 0.72f;
    float t = size * 0.06f;
    float y0 = y + (size - h) * 0.5f;
    float cx = x + w * 0.5f;
    float cy = y0 + h * 0.5f;

    thick_line(gs, x, y0, x + w, y0, t, z, color);
    thick_line(gs, x + w, y0, x + w, y0 + h, t, z, color);
    thick_line(gs, x + w, y0 + h, x, y0 + h, t, z, color);
    thick_line(gs, x, y0 + h, x, y0, t, z, color);

    if (glyph == PS2_GLYPH_START || glyph == PS2_GLYPH_SELECT) {
        int chevrons = glyph == PS2_GLYPH_START ? 1 : 2;
        int i;
        for (i = 0; i < chevrons; ++i) {
            float ox = ((float)i - (float)(chevrons - 1) * 0.5f) * size * 0.28f;
            thick_line(gs, cx - size * 0.12f + ox, cy - size * 0.16f,
                cx + size * 0.14f + ox, cy, t, z, color);
            thick_line(gs, cx + size * 0.14f + ox, cy,
                cx - size * 0.12f + ox, cy + size * 0.16f, t, z, color);
        }
    } else {
        boolean right = glyph == PS2_GLYPH_R1 || glyph == PS2_GLYPH_R2;
        boolean second = glyph == PS2_GLYPH_L2 || glyph == PS2_GLYPH_R2;
        float stem_x = x + (right ? w * 0.67f : w * 0.33f);
        float digit_x = x + (right ? w * 0.34f : w * 0.66f);
        /* Minimal L/R mnemonic: outer vertical plus one/two small ticks. */
        thick_line(gs, stem_x, y0 + h * 0.24f, stem_x, y0 + h * 0.76f, t, z, color);
        thick_line(gs, stem_x, y0 + h * 0.76f,
            stem_x + (right ? -1.0f : 1.0f) * size * 0.18f,
            y0 + h * 0.76f, t, z, color);
        thick_line(gs, digit_x - size * 0.09f, cy, digit_x + size * 0.09f, cy, t, z, color);
        if (second)
            thick_line(gs, digit_x - size * 0.09f, cy + size * 0.15f,
                digit_x + size * 0.09f, cy + size * 0.15f, t, z, color);
    }
}

static void draw_dpad_arrow(GSGLOBAL *gs, Ps2Glyph glyph, float x, float y, float size, int z)
{
    const u64 color = glyph_color(glyph);
    float cx = x + size * 0.5f;
    float cy = y + size * 0.5f;
    float r = size * 0.30f;
    float t = size * 0.08f;

    switch (glyph) {
        case PS2_GLYPH_DPAD_UP:
            thick_line(gs, cx, cy - r, cx - r, cy + r * 0.2f, t, z, color);
            thick_line(gs, cx, cy - r, cx + r, cy + r * 0.2f, t, z, color);
            break;
        case PS2_GLYPH_DPAD_DOWN:
            thick_line(gs, cx, cy + r, cx - r, cy - r * 0.2f, t, z, color);
            thick_line(gs, cx, cy + r, cx + r, cy - r * 0.2f, t, z, color);
            break;
        case PS2_GLYPH_DPAD_LEFT:
            thick_line(gs, cx - r, cy, cx + r * 0.2f, cy - r, t, z, color);
            thick_line(gs, cx - r, cy, cx + r * 0.2f, cy + r, t, z, color);
            break;
        case PS2_GLYPH_DPAD_RIGHT:
            thick_line(gs, cx + r, cy, cx - r * 0.2f, cy - r, t, z, color);
            thick_line(gs, cx + r, cy, cx - r * 0.2f, cy + r, t, z, color);
            break;
        default:
            break;
    }
}

void Ps2Glyph_SetDrawTransform(
    float x_scale,
    float y_scale,
    float x_offset,
    float y_offset)
{
    g_x_scale = x_scale;
    g_y_scale = y_scale;
    g_x_offset = x_offset;
    g_y_offset = y_offset;
}

void Ps2Glyph_Draw(
    GSGLOBAL *gs,
    Ps2Glyph glyph,
    float x,
    float y,
    float size,
    int z)
{
    if (gs == NULL || size <= 0.0f)
        return;

    if (glyph <= PS2_GLYPH_TRIANGLE)
        draw_face(gs, glyph, x, y, size, z);
    else if (glyph <= PS2_GLYPH_R2)
        draw_label_box(gs, glyph, x, y, size, z);
    else
        draw_dpad_arrow(gs, glyph, x, y, size, z);
}

const char *Ps2Glyph_Name(Ps2Glyph glyph)
{
    switch (glyph) {
        case PS2_GLYPH_CROSS: return "Cross";
        case PS2_GLYPH_CIRCLE: return "Circle";
        case PS2_GLYPH_SQUARE: return "Square";
        case PS2_GLYPH_TRIANGLE: return "Triangle";
        case PS2_GLYPH_START: return "Start";
        case PS2_GLYPH_SELECT: return "Select";
        case PS2_GLYPH_L1: return "L1";
        case PS2_GLYPH_R1: return "R1";
        case PS2_GLYPH_L2: return "L2";
        case PS2_GLYPH_R2: return "R2";
        case PS2_GLYPH_DPAD_UP: return "D-pad Up";
        case PS2_GLYPH_DPAD_DOWN: return "D-pad Down";
        case PS2_GLYPH_DPAD_LEFT: return "D-pad Left";
        case PS2_GLYPH_DPAD_RIGHT: return "D-pad Right";
        default: return "Button";
    }
}
