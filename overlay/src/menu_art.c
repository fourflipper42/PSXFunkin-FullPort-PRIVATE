#include "menu_art.h"
#include "framebank.h"
#include "timer.h"

typedef struct {
    const char *path;
    u16 x, y, clut_y;
    const u16 *idle;
    u16 idle_count;
    const u16 *selected;
    u16 selected_count;
} MenuArtDef;
#include "menu_art_generated.h"

static FrameBank banks[COUNT_OF(menu_art_defs)], backgrounds[4], prompts[2];
static Gfx_Tex small_font;
static fixed_t elapsed;
static int previous_selection;

void MenuArt_Load(void)
{
    unsigned int i;
    /* All CD reads precede menu music. No seek on selection/page changes. */
    for (i = 0; i < COUNT_OF(banks); i++) {
        const MenuArtDef *d = &menu_art_defs[i];
        FrameBank_Load(&banks[i], d->path, d->x, d->y, 0, d->clut_y);
    }
    FrameBank_Load(&backgrounds[0], "\\MENU\\BACK0.FBK;1", 384, 256, 0, 489);
    FrameBank_Load(&backgrounds[1], "\\MENU\\BACK1.FBK;1", 512, 256, 0, 490);
    FrameBank_Load(&backgrounds[2], "\\MENU\\BACK2.FBK;1", 640, 256, 0, 491);
    FrameBank_Load(&backgrounds[3], "\\MENU\\BACK3.FBK;1", 896, 0, 0, 492);
    FrameBank_Load(&prompts[0], "\\MENU\\PROMPT0.FBK;1", 384, 256, 0, 493);
    FrameBank_Load(&prompts[1], "\\MENU\\PROMPT1.FBK;1", 512, 256, 0, 494);
    Gfx_LoadTex(&small_font, IO_Read("\\MENU\\SMALL.TIM;1"), GFX_LOADTEX_FREE);
    MenuArt_Enter();
}
void MenuArt_Free(void)
{
    unsigned int i;
    for (i = 0; i < COUNT_OF(banks); i++) FrameBank_Free(&banks[i]);
    for (i = 0; i < COUNT_OF(backgrounds); i++) FrameBank_Free(&backgrounds[i]);
    for (i = 0; i < COUNT_OF(prompts); i++) FrameBank_Free(&prompts[i]);
}
void MenuArt_Enter(void)
{
    unsigned int i;
    /* Title and main labels deliberately share texture pages, never a frame. */
    for (i = 0; i < COUNT_OF(banks); i++) FrameBank_Invalidate(&banks[i]);
    for (i = 0; i < COUNT_OF(backgrounds); i++) FrameBank_Invalidate(&backgrounds[i]);
    for (i = 0; i < COUNT_OF(prompts); i++) FrameBank_Invalidate(&prompts[i]);
    elapsed = 0;
    previous_selection = -1;
}
void MenuArt_Tick(int selected)
{
    if (selected != previous_selection) elapsed = 0;
    else elapsed += timer_dt;
    /* Keep multiplication bounded during long unattended menu sessions. */
    if (elapsed >= FIXED_DEC(3600,1)) elapsed = 0;
    previous_selection = selected;
}
void MenuArt_Label(int item, int selected, int cx, int cy)
{
    const MenuArtDef *d = &menu_art_defs[item];
    FrameBank *b = &banks[item];
    const u16 *sequence = selected ? d->selected : d->idle;
    unsigned int count = selected ? d->selected_count : d->idle_count;
    unsigned int index = ((elapsed * 24) >> FIXED_SHIFT) % count;
    FrameBank_Draw(b, sequence[index], cx - b->info.width / 2, cy - b->info.height / 2);
}
void MenuArt_Title(unsigned int song_ms)
{
    /* Gettin' Freaky: 102 BPM. Alternate the two 15-frame dance halves. */
    unsigned int beat = song_ms * 102 / 60000;
    unsigned int phase = (song_ms * 102 % 60000) * 24 / 102000;
    unsigned int frame = phase < 15 ? phase : 14;
    FrameBank_Draw(&banks[5], menu_art_defs[5].idle[frame], -20, -10);
    FrameBank_Draw(&banks[6], menu_art_defs[6].idle[frame + ((beat & 1) ? 15 : 0)], 145, 24);
}
void MenuArt_Prompt(int confirming, fixed_t time)
{
    const u16 *sequence = confirming ? menu_prompt_confirm : menu_prompt_idle;
    unsigned int count = confirming ? COUNT_OF(menu_prompt_confirm) : COUNT_OF(menu_prompt_idle);
    unsigned int frame = ((time * 24) >> FIXED_SHIFT) % count;
    int x = 160 - prompts[0].info.width;
    FrameBank_Draw(&prompts[0], sequence[frame], x, 188);
    FrameBank_Draw(&prompts[1], sequence[frame], 160, 188);
}
void MenuArt_MainBack(int camera_y, int magenta)
{
    unsigned int i;
    for (i = 0; i < COUNT_OF(backgrounds); i++)
        FrameBank_Draw(&backgrounds[i], !!magenta, -32 + (i & 1) * 192, -24 + (i >> 1) * 144 - camera_y * 17 / 100);
}
void MenuArt_Back(void) { MenuArt_MainBack(0, 0); }
void MenuArt_Text(const char *text, int x, int y, int center, int bright)
{
    int length;
    u8 color = bright ? 128 : 75;
    if (!text || y < 12 || y + 12 > 228) return;
    length = strlen(text);
    if (center) x -= length * 4;
    for (; *text; text++, x += 8) {
        unsigned int ch = (unsigned char)*text;
        RECT src;
        if (x < 12 || x + 8 > 308 || ch == ' ') continue;
        if (ch < 32 || ch > 127) ch = '?';
        ch -= 32;
        src.x = (ch & 15) * 8; src.y = (ch >> 4) * 12;
        src.w = 8; src.h = 12;
        Gfx_BlitTexCol(&small_font, &src, x, y, color, color, color);
        /* Ordering table is reversed: enqueue the shadow after the glyph. */
        Gfx_BlitTexCol(&small_font, &src, x + 1, y + 1, 0, 0, 0);
    }
}
unsigned int MenuArt_CreditCount(void) { return COUNT_OF(menu_credits); }
const char *MenuArt_Credit(unsigned int line)
{
    return line < COUNT_OF(menu_credits) ? menu_credits[line] : "";
}
