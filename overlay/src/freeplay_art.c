#include "freeplay_art.h"
#include "framebank.h"
#include "freeplay_art_generated.h"

static FrameBank dj, selected, capsule, backgrounds[2], difficulty, albums, filters;
static Gfx_Tex font, icons[2], ui[4];
static int current_song, current_filter, current_diff, previous_album;
static unsigned int favorite_songs;
static unsigned int best_score, best_completion;
static fixed_t arrow_time[2], album_time, last_elapsed;

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
    FrameBank_Load(&albums, "\\FREEPLAY\\ALBUMS.FBK;1", 832, 0, 0, 490);
    FrameBank_Load(&filters, "\\FREEPLAY\\FILTERS.FBK;1", 832, 112, 0, 491);
    Gfx_LoadTex(&ui[0], IO_Read("\\FREEPLAY\\UI0.TIM;1"), GFX_LOADTEX_FREE);
    Gfx_LoadTex(&ui[1], IO_Read("\\FREEPLAY\\UI1.TIM;1"), GFX_LOADTEX_FREE);
    Gfx_LoadTex(&ui[2], IO_Read("\\FREEPLAY\\UI2.TIM;1"), GFX_LOADTEX_FREE);
    Gfx_LoadTex(&ui[3], IO_Read("\\FREEPLAY\\UI3.TIM;1"), GFX_LOADTEX_FREE);
    Gfx_LoadTex(&font, IO_Read("\\FREEPLAY\\FONT.TIM;1"), GFX_LOADTEX_FREE);
    Gfx_LoadTex(&icons[0], IO_Read("\\FREEPLAY\\ICONS0.TIM;1"), GFX_LOADTEX_FREE);
    Gfx_LoadTex(&icons[1], IO_Read("\\FREEPLAY\\ICONS1.TIM;1"), GFX_LOADTEX_FREE);
    current_song=-1; current_filter=2; previous_album=-1; current_diff=1;
    arrow_time[0]=arrow_time[1]=-1024; last_elapsed=album_time=0;
}
void FreeplayArt_Free(void)
{
    FrameBank_Free(&dj); FrameBank_Free(&selected); FrameBank_Free(&capsule);
    FrameBank_Free(&backgrounds[0]); FrameBank_Free(&backgrounds[1]); FrameBank_Free(&difficulty);
    FrameBank_Free(&albums);
    FrameBank_Free(&filters);
}
void FreeplayArt_State(int song, int filter, unsigned int favorites, int direction, fixed_t elapsed)
{
    if (elapsed<last_elapsed) previous_album=-1;
    if (direction) arrow_time[direction>0]=elapsed;
    current_song=song; current_filter=filter; favorite_songs=favorites; last_elapsed=elapsed;
}
void FreeplayArt_Results(unsigned int score, unsigned int completion)
{
    best_score=score>9999999 ? 9999999 : score;
    best_completion=completion>100 ? 100 : completion;
}
static void Sprite(unsigned int index, int x, int y, int bright)
{
    const FreeplaySprite *s=&freeplay_sprites[index];
    RECT source={s->x,s->y,s->w,s->h};
    Gfx_BlitTexCol(&ui[s->page],&source,x+s->dx,y+s->dy,bright,bright,bright);
}
static void BackText(const char *text,int x,int y,int white)
{
    int right=146-y*44/240;
    for(;*text;text++,x+=9) {
        unsigned int c=(unsigned char)*text;
        if(c<32 || c>=96 || *text==' ' || x>=right || x+12<0)continue;
        const FreeplaySprite *s=&freeplay_sprites[fp_backglyph[c-32]];
        RECT r={s->x,s->y,s->w,s->h};int dx=x+s->dx;
        if(dx<0) {r.x-=dx;r.w+=dx;dx=0;}
        if(dx+r.w>right)r.w=right-dx;
        if(r.w>0)Gfx_BlitTexCol(&ui[s->page],&r,dx,y+s->dy,white?128:117,white?121:77,white?91:39);
    }
}
static void Number(const u16 *const *digits, const u16 *counts, unsigned int value, int length, int x, int y, int advance, unsigned int frame, int bright)
{
    for(int i=length-1;i>=0;i--) {
        unsigned int digit=value%10;value/=10;
        Sprite(digits[digit][frame<counts[digit] ? frame : counts[digit]-1],x+i*advance,y,bright);
    }
}
static void TextClip(const char *name, int x, int y, int bright, int left, int right)
{
    int color = bright ? 128 : 80;
    if (y < 8 || y + 14 > 240) return;
    for (; *name; name++, x += 6) {
        unsigned int c = (unsigned char)*name;
        RECT source;
        if (x + 8 <= left || x >= right || c == ' ') continue;
        if (c < 32 || c > 127) c = '?';
        c -= 32;
        source.x = (c & 15) * 8; source.y = (c >> 4) * 14;
        source.w = 8; source.h = 14;
        int dx = x;
        if (dx < left) {source.x += left-dx;source.w -= left-dx;dx=left;}
        if (dx + source.w > right) source.w=right-dx;
        Gfx_BlitTexCol(&font, &source, dx, y, color, color, color);
        if (bright && dx + source.w < right) Gfx_BlitTexCol(&font, &source, dx + 1, y, 0, 70, 100);
    }
}
static void Text(const char *name, int x, int y, int bright) {TextClip(name,x,y,bright,8,312);}
void FreeplayArt_Song(const char *name, int song, int is_selected, fixed_t offset, fixed_t elapsed, fixed_t confirm_elapsed)
{
    static const u8 song_icons[] = {11,1,1,1,2,2,3,4,4,4,5,5,5,6,6,3,7,7,8,9,9,9,10,10,10,10};
    /* Curved capsule column. Continuous positions allow a smooth selection
     * change without a frame bank, allocation or CD access per song. */
    int y = 138 + (offset * 38 >> FIXED_SHIFT);
    static const s8 curve[] = {-2,-8,-7,0,7,8,1,-6};
    int row = offset >> FIXED_SHIFT;
    int x;
    FrameBank *bank = is_selected ? &selected : &capsule;
    if (y > 232 || y + 31 < 62) return;
    x = 92 + curve[row + 3] + ((curve[row + 4] - curve[row + 3]) * (offset & 1023) >> FIXED_SHIFT);
    if (song >= 0) {
        name=fp_song_names[song];
        unsigned int icon = song_icons[song];
        unsigned int pose = freeplay_icon_idle[icon];
        if (is_selected && confirm_elapsed >= 0)
            pose = freeplay_icon_confirm[icon][((confirm_elapsed * 24) >> FIXED_SHIFT) % freeplay_icon_counts[icon]];
        RECT source = {(pose % 48 % 6) * 40, (pose % 48 / 6) * 32, 40, 32};
        Gfx_BlitTex(&icons[pose / 48], &source, x - 8, y - 1);
        if (favorite_songs & (1u<<song)) Sprite(fp_heart[COUNT_OF(fp_heart)-1],x+88,y+8,128);
        Number(fp_ratings,fp_rating_counts,fp_song_rating[song][current_diff],2,x+112,y+6,7,0,128);
        Number(fp_bpms,fp_bpm_counts,fp_song_bpm[song][current_diff],3,x+43,y+21,3,0,128);
        Sprite(fp_bpmtext[0],x+33,y+21,128);
        Sprite(fp_difficultytext[0],x+96,y+21,128);
        Sprite(fp_weeks[fp_song_week[song]],x+64,y+21,128);
    }
    int scroll = 0;
    int excess = (int)strlen(name) * 6 - 77;
    if (is_selected && excess > 0) {
        int distance = (elapsed * 18 >> FIXED_SHIFT) % (excess * 2 + 72);
        if (distance > 36 && distance < excess + 36) scroll = distance - 36;
        else if (distance >= excess + 36 && distance < excess + 72) scroll = excess;
        else if (distance >= excess + 72) scroll = excess * 2 + 72 - distance;
    }
    TextClip(name, x + 34 - scroll, y + 5, is_selected, x + 34, x + 111);
    FrameBank_Draw(bank, ((elapsed * 24) >> FIXED_SHIFT) % bank->info.frames, x, y);
}
void FreeplayArt_UI(int diff, fixed_t elapsed)
{
    static const u16 *const diffs[] = {freeplay_diff_easy, freeplay_diff_normal,
        freeplay_diff_hard, freeplay_diff_erect, freeplay_diff_nightmare};
    static const u16 counts[] = {COUNT_OF(freeplay_diff_easy), COUNT_OF(freeplay_diff_normal),
        COUNT_OF(freeplay_diff_hard), COUNT_OF(freeplay_diff_erect), COUNT_OF(freeplay_diff_nightmare)};
    unsigned int frame = (elapsed * 24) >> FIXED_SHIFT;
    current_diff=diff;
    int album=current_song<0 ? -1 : fp_song_album[current_song][diff];
    if(album!=previous_album) {album_time=elapsed;previous_album=album;}
    Sprite((elapsed-arrow_time[0]<85 ? fp_arrow_left_press : fp_arrow_left)[frame%COUNT_OF(fp_arrow_left)],5,31,128);
    Sprite((elapsed-arrow_time[1]<85 ? fp_arrow_right_press : fp_arrow_right)[frame%COUNT_OF(fp_arrow_right)],113,31,128);
    for(int i=0;i<5;i++) {
        int filter=(current_filter+i+10)%12;
        if (i==2) FrameBank_Draw(&filters,fp_filter_anims[filter][frame%fp_filter_anim_counts[filter]],123+i*20,29);
        else Sprite(fp_filters[filter][0],123+i*20,29,94);
        if(i<4) Sprite(fp_separator[0],144+i*20,43,100);
    }
    Sprite(fp_mini_left[0],122,43,128);Sprite(fp_mini_right[0],226,43,128);
    Sprite(fp_highscore[(frame%720)<COUNT_OF(fp_highscore) ? frame%720 : COUNT_OF(fp_highscore)-1],229,30,128);
    Sprite(fp_clearbox[0],292,30,128);
    Sprite(fp_completion[best_completion],296,36,128);
    Number(fp_digits,fp_digit_counts,best_score,7,221,49,13,frame,128);
    Sprite(fp_header[0],8,8,128);
    Sprite(fp_ost[0],234,8,128);
    Text("L1/R1 FILTER  [] FAV", 8,226,0);
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
    FrameBank_Draw(&dj, pose, 0, 35);
    if (current_song>=0) {
        unsigned int album=fp_song_album[current_song][diff];
        unsigned int age=((elapsed-album_time)*24)>>FIXED_SHIFT;
        unsigned int count=fp_album_switch_counts[album];
        unsigned int f=age<count ? fp_album_switch[album][age] : fp_album_idle[album][(age-count)%fp_album_idle_counts[album]];
        unsigned int title_count=fp_titles_switch_counts[album];
        unsigned int title=age<title_count ? fp_titles_switch[album][age] : fp_titles_idle[album][(age-title_count)%fp_titles_idle_counts[album]];
        Sprite(title,208+fp_title_offsets[album][0],181+fp_title_offsets[album][1],128);
        FrameBank_Draw(&albums,f,208,80);
    }
    for(int i=0;i<7;i++) {
        static const char *const lines[]={"HOT BLOODED IN MORE WAYS THAN ONE ","BOYFRIEND ","PROTECT YO NUTS "};
        const char *line=lines[i%3];int width=strlen(line)*9;
        int scroll=(elapsed*(i%2 ? 13 : 18)>>FIXED_SHIFT)%width;
        for(int x=-scroll;x<146;x+=width)BackText(line,x,65+i*24,i%3!=1);
    }
    FrameBank_Draw(&backgrounds[0], 0, 0, 0);
    FrameBank_Draw(&backgrounds[1], 0, 160, 0);
}
