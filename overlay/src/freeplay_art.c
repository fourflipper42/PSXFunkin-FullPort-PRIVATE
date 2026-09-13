#include "freeplay_art.h"
#include "framebank.h"
#include "freeplay_art_generated.h"

static FrameBank dj, selected, capsule, backgrounds[2], difficulty;
static Gfx_Tex font, icons[2];

void FreeplayArt_Load(void)
{
    /* These pages never coexist with title/main artwork. Each sprite that can
     * show a different frame in the same draw list has its own VRAM region. */
    FrameBank_Load(&dj, "\\FREEPLAY\\DJ.FBK;1", 384, 0, 0, 482);
    FrameBank_Load(&selected, "\\FREEPLAY\\SELECTED.FBK;1", 512, 0, 0, 483);
    FrameBank_Load(&capsule, "\\FREEPLAY\\CAPSULE.FBK;1", 640, 0, 0, 484);
    FrameBank_Load(&backgrounds[0], "\\FREEPLAY\\BACK0.FBK;1", 384, 256, 0, 485);
    FrameBank_Load(&backgrounds[1], "\\FREEPLAY\\BACK1.FBK;1", 512, 256, 0, 486);
    FrameBank_Load(&difficulty, "\\FREEPLAY\\DIFF.FBK;1", 768, 0, 0, 487);
    Gfx_LoadTex(&font, IO_Read("\\FREEPLAY\\FONT.TIM;1"), GFX_LOADTEX_FREE);
    Gfx_LoadTex(&icons[0], IO_Read("\\FREEPLAY\\ICONS0.TIM;1"), GFX_LOADTEX_FREE);
    Gfx_LoadTex(&icons[1], IO_Read("\\FREEPLAY\\ICONS1.TIM;1"), GFX_LOADTEX_FREE);
}
void FreeplayArt_Free(void)
{
    FrameBank_Free(&dj); FrameBank_Free(&selected); FrameBank_Free(&capsule);
    FrameBank_Free(&backgrounds[0]); FrameBank_Free(&backgrounds[1]); FrameBank_Free(&difficulty);
}
static void Text(const char *name, int x, int y, int bright)
{
    int color = bright ? 128 : 80;
    if (y < 8 || y + 14 > 232) return;
    for (; *name; name++, x += 6) {
        unsigned int c = (unsigned char)*name;
        RECT source;
        if (x < 8 || x + 8 > 312 || c == ' ') continue;
        if (c < 32 || c > 127) c = '?';
        c -= 32;
        source.x = (c & 15) * 8; source.y = (c >> 4) * 14;
        source.w = 8; source.h = 14;
        Gfx_BlitTexCol(&font, &source, x, y, color, color, color);
        if (bright) Gfx_BlitTexCol(&font, &source, x + 1, y, 0, 70, 100);
    }
}
void FreeplayArt_Song(const char *name, int song, int is_selected, fixed_t offset, fixed_t elapsed, fixed_t confirm_elapsed)
{
    static const u8 song_icons[] = {0,1,1,1,2,2,3,4,4,4,5,5,5,6,6,3,7,7,8,9,9,9,10,10,10,10};
    /* Curved capsule column. Continuous positions allow a smooth selection
     * change without a frame bank, allocation or CD access per song. */
    int y = 68 + (offset * 44 >> FIXED_SHIFT);
    static const s8 curve[] = {-2,-14,-13,0,13,14,2,-11};
    int row = offset >> FIXED_SHIFT;
    int x;
    FrameBank *bank = is_selected ? &selected : &capsule;
    if (y > 232 || y + 40 < 8) return;
    x = 112 + curve[row + 3] + ((curve[row + 4] - curve[row + 3]) * (offset & 1023) >> FIXED_SHIFT);
    unsigned int icon = song_icons[song];
    unsigned int pose = freeplay_icon_idle[icon];
    if (is_selected && confirm_elapsed >= 0)
        pose = freeplay_icon_confirm[icon][((confirm_elapsed * 24) >> FIXED_SHIFT) % freeplay_icon_counts[icon]];
    RECT source = {(pose % 48 % 6) * 40, (pose % 48 / 6) * 32, 40, 32};
    Gfx_BlitTex(&icons[pose / 48], &source, x + 4, y + 3);
    Text(name, x + 45, y + 10, is_selected);
    FrameBank_Draw(bank, ((elapsed * 24) >> FIXED_SHIFT) % bank->info.frames, x, y);
}
void FreeplayArt_UI(int diff, fixed_t elapsed)
{
    static const u16 *const diffs[] = {freeplay_diff_easy, freeplay_diff_normal,
        freeplay_diff_hard, freeplay_diff_erect, freeplay_diff_nightmare};
    static const u16 counts[] = {COUNT_OF(freeplay_diff_easy), COUNT_OF(freeplay_diff_normal),
        COUNT_OF(freeplay_diff_hard), COUNT_OF(freeplay_diff_erect), COUNT_OF(freeplay_diff_nightmare)};
    unsigned int frame = (elapsed * 24) >> FIXED_SHIFT;
    Text("<", 8, 37, 1); Text(">", 108, 37, 1);
    Text("FREEPLAY", 12, 12, 1);
    Text("X: PLAY  O: BACK", 210, 216, 1);
    FrameBank_Draw(&difficulty, diffs[diff][frame % counts[diff]], 16, 30);
}
void FreeplayArt_Back(int diff, fixed_t elapsed, int confirming, fixed_t confirm_elapsed)
{
    unsigned int frame = (elapsed * 24) >> FIXED_SHIFT;
    unsigned int pose;
    if (confirming) {
        unsigned int f = (confirm_elapsed * 24) >> FIXED_SHIFT;
        if (f >= COUNT_OF(freeplay_dj_confirm)) f = COUNT_OF(freeplay_dj_confirm) - 1;
        pose = freeplay_dj_confirm[f];
    } else if (frame < COUNT_OF(freeplay_dj_intro)) pose = freeplay_dj_intro[frame];
    else pose = freeplay_dj_idle[(frame - COUNT_OF(freeplay_dj_intro)) % COUNT_OF(freeplay_dj_idle)];
    FrameBank_Draw(&dj, pose, 0, 0);
    FrameBank_Draw(&backgrounds[0], 0, 0, 0);
    FrameBank_Draw(&backgrounds[1], 0, 160, 0);
}
