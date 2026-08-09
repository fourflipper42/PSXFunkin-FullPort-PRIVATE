#!/usr/bin/env python3
"""Apply the complete official LE SSERAFIM collaboration after Weekend 1."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


SSERAFIM_H = r'''#ifndef _SSERAFIM_H
#define _SSERAFIM_H

#include "../stage.h"

StageBack *Back_Sserafim_New(void);
boolean Sserafim_ApplyHit(const Note *note);
void Sserafim_ApplyMiss(const Note *note);
void Sserafim_ApplyCameraTarget(void);
void Sserafim_ApplyCameraZoom(void);
boolean Sserafim_DrawHealthIcon(s8 side);
void Sserafim_Reset(StageId id);
void Sserafim_PlayIntro(StageId id);
void Sserafim_Exit(void);

#endif
'''


SSERAFIM_C = r'''#include "sserafim.h"

#include "../archive.h"
#include "../audio.h"
#include "../main.h"
#include "../mem.h"
#include "../movie.h"
#include "../random.h"
#include "../timer.h"

#include "../character/sfkazuha.h"
#include "../character/sfsakura.h"
#include "../character/sfgf.h"
#include "../sserafim_movies_generated.h"

typedef struct
{
    u16 step;
    u8 kind, flags;
    s16 a, b, c, d;
    u32 color0, color1;
} SserafimEvent;

typedef struct
{
    u8 tex;
    RECT src;
} SserafimSpriteFrame;

#include "../sserafim_events_generated.h"
#include "../sserafim_assets_generated.h"

enum
{
    SFEvent_Focus = 1,
    SFEvent_Zoom,
    SFEvent_Bop,
    SFEvent_Show,
    SFEvent_Sing,
    SFEvent_Dark,
    SFEvent_Lights,
    SFEvent_Cover,
    SFEvent_Flash,
    SFEvent_Pulse,
    SFEvent_Kick,
    SFEvent_Beautiful,
    SFEvent_End,
    SFEvent_Vibration,
    SFEvent_HealthIcon,
};

typedef struct
{
    StageBack back;
    Gfx_Tex tex_left, tex_right, tex_extra[3], tex_fx;
    IO_Data extra_arc[3];
    IO_Data extra_pages[3][8];
    u8 extra_page[3];
    u8 extra_dir[3];
    fixed_t extra_hold[3];
    u8 visible_mask, singing_mask;
    u16 event_index;
    boolean focus_active, cover, pulse_enabled, beautiful;
    boolean opponent_icon_visible, ending_played;
    s16 focus_x, focus_y;
    fixed_t zoom;
    u8 bop_rate, bop_intensity, bop_offset;
    u8 dark_amount, light_strength;
    fixed_t light_timer, flash_timer, pulse_timer, shake_timer;
    u32 pulse_color[2];
    u16 pulse_duration[2];
    u8 pulse_intensity[2], pulse_index;
    u8 player_icon, opponent_icon;
    u8 yunjin_kick, kick_frame, kick_tick;
    u16 dust_phase;
} Back_Sserafim;

static Back_Sserafim *sf_back = NULL;
static boolean sf_session_active = false;

static const char *const sf_yunjin_pages[] = {
    "yu00.tim", "yu01.tim", "yu02.tim", "yu03.tim", "yu04.tim", "yu05.tim", "yu06.tim", NULL
};
static const char *const sf_chaewon_pages[] = {"ch00.tim", "ch01.tim", NULL};
static const char *const sf_eunchae_pages[] = {"eu00.tim", "eu01.tim", NULL};

static const SserafimSpriteFrame *SF_ExtraFrame(Back_Sserafim *this, u8 girl)
{
    if (girl == 0 && this->yunjin_kick)
    {
        if (this->yunjin_kick == 1)
            return &sf_yunjin_kick1[this->kick_frame % SF_YUNJIN_KICK1_COUNT];
        return &sf_yunjin_kick2[this->kick_frame % SF_YUNJIN_KICK2_COUNT];
    }
    switch (girl)
    {
        case 0:
            switch (this->extra_dir[0]) {
                case 1: return sf_yunjin_left; case 2: return sf_yunjin_down;
                case 3: return sf_yunjin_up; case 4: return sf_yunjin_right;
                default: return sf_yunjin_idle;
            }
        case 1:
            switch (this->extra_dir[1]) {
                case 1: return sf_chaewon_left; case 2: return sf_chaewon_down;
                case 3: return sf_chaewon_up; case 4: return sf_chaewon_right;
                default: return sf_chaewon_idle;
            }
        default:
            switch (this->extra_dir[2]) {
                case 1: return sf_eunchae_left; case 2: return sf_eunchae_down;
                case 3: return sf_eunchae_up; case 4: return sf_eunchae_right;
                default: return sf_eunchae_idle;
            }
    }
}

static void SF_DrawExtra(Back_Sserafim *this, u8 girl, fixed_t x, fixed_t y)
{
    const SserafimSpriteFrame *frame = SF_ExtraFrame(this, girl);
    if (frame->tex != this->extra_page[girl])
    {
        this->extra_page[girl] = frame->tex;
        Gfx_LoadTex(&this->tex_extra[girl], this->extra_pages[girl][frame->tex], 0);
    }
    RECT_FIXED dst = {x - stage.camera.x, y - stage.camera.y, FIXED_DEC(128,1), FIXED_DEC(128,1)};
    Stage_DrawTex(&this->tex_extra[girl], &frame->src, &dst, stage.camera.bzoom);
}

static void SF_UpdateAnimations(Back_Sserafim *this)
{
    for (u8 i = 0; i < 3; i++)
    {
        if (this->extra_hold[i] > 0)
        {
            this->extra_hold[i] -= timer_dt;
            if (this->extra_hold[i] <= 0)
                this->extra_dir[i] = 0;
        }
    }
    if (this->yunjin_kick)
    {
        u8 speed = this->yunjin_kick == 1 ? 5 : 10;
        u8 count = this->yunjin_kick == 1 ? SF_YUNJIN_KICK1_COUNT : SF_YUNJIN_KICK2_COUNT;
        if (++this->kick_tick >= speed)
        {
            this->kick_tick = 0;
            if (++this->kick_frame >= count)
            {
                this->kick_frame = count - 1;
                this->yunjin_kick = 0;
            }
        }
    }
}

static void Back_Sserafim_DrawMD(StageBack *back)
{
    Back_Sserafim *this = (Back_Sserafim*)back;
    SF_UpdateAnimations(this);
    if (this->visible_mask & (1 << 0)) SF_DrawExtra(this, 0, FIXED_DEC(-280,1), FIXED_DEC(-95,1));
    if (this->visible_mask & (1 << 2)) SF_DrawExtra(this, 1, FIXED_DEC(-25,1), FIXED_DEC(-100,1));
    if (this->visible_mask & (1 << 3)) SF_DrawExtra(this, 2, FIXED_DEC(15,1), FIXED_DEC(12,1));
}

static void SF_DrawFXCell(Back_Sserafim *this, RECT src, fixed_t x, fixed_t y)
{
    RECT_FIXED dst = {x - stage.camera.x, y - stage.camera.y, FIXED_DEC(128,1), FIXED_DEC(128,1)};
    Stage_DrawTex(&this->tex_fx, &src, &dst, stage.camera.bzoom);
}

static void Back_Sserafim_DrawFG(StageBack *back)
{
    Back_Sserafim *this = (Back_Sserafim*)back;
    this->dust_phase += 2;
    RECT dust = {128,128,128,128};
    for (u8 i = 0; i < 4; i++)
    {
        fixed_t x = FIXED_DEC(-300 + ((this->dust_phase + i * 155) % 620),1);
        SF_DrawFXCell(this, dust, x, FIXED_DEC(-20 + i * 27,1));
    }
    if (this->light_timer > 0)
    {
        RECT truck1 = {0,0,128,128};
        RECT truck2 = {128,0,128,128};
        SF_DrawFXCell(this, truck1, FIXED_DEC(-190,1), FIXED_DEC(-115,1));
        SF_DrawFXCell(this, truck2, FIXED_DEC(-70,1), FIXED_DEC(-80,1));
        this->light_timer -= timer_dt;
    }
    RECT screen = {0,0,SCREEN_WIDTH,SCREEN_HEIGHT};
    if (this->dark_amount >= 32)
        Gfx_DrawRectSemi(&screen, 0, 0, 0, this->dark_amount >= 160 ? 2 : 0);
    if (this->pulse_timer > 0 && !stage.reduced_flashing)
    {
        u32 color = this->pulse_color[this->pulse_index & 1];
        Gfx_DrawRectSemi(&screen, (color >> 16) & 0x7F, (color >> 8) & 0x7F, color & 0x7F, 1);
        this->pulse_timer -= timer_dt;
    }
    if (this->flash_timer > 0 && !stage.reduced_flashing)
    {
        Gfx_DrawRectSemi(&screen, 0x7F, 0x7F, 0x7F, 1);
        this->flash_timer -= timer_dt;
    }
    if (this->cover)
        Gfx_DrawRect(&screen, 0, 0, 0);
}

static void Back_Sserafim_DrawBG(StageBack *back)
{
    Back_Sserafim *this = (Back_Sserafim*)back;
    const RECT src = {0,0,256,240};
    RECT_FIXED dst = {FIXED_DEC(-256,1)-stage.camera.x,FIXED_DEC(-120,1)-stage.camera.y,FIXED_DEC(256,1),FIXED_DEC(240,1)};
    Stage_DrawTex(&this->tex_left,&src,&dst,stage.camera.bzoom);
    dst.x += FIXED_DEC(256,1);
    Stage_DrawTex(&this->tex_right,&src,&dst,stage.camera.bzoom);
}

static void Back_Sserafim_Free(StageBack *back)
{
    Back_Sserafim *this = (Back_Sserafim*)back;
    for (u8 i=0;i<3;i++) Mem_Free(this->extra_arc[i]);
    if (sf_back == this) sf_back = NULL;
    Mem_Free(this);
}

static void SF_LoadExtra(Back_Sserafim *this, u8 girl, const char *path, const char *const *names)
{
    this->extra_arc[girl] = IO_Read(path);
    u8 index = 0;
    while (*names != NULL)
        this->extra_pages[girl][index++] = Archive_Find(this->extra_arc[girl], *names++);
    this->extra_page[girl] = 0xFF;
}

StageBack *Back_Sserafim_New(void)
{
    Back_Sserafim *this = Mem_Alloc(sizeof(Back_Sserafim));
    if (this == NULL) return NULL;
    this->back.draw_fg=Back_Sserafim_DrawFG;
    this->back.draw_md=Back_Sserafim_DrawMD;
    this->back.draw_bg=Back_Sserafim_DrawBG;
    this->back.free=Back_Sserafim_Free;
    IO_Data arc=IO_Read("\\SSERAFIM\\BACK.ARC;1");
    Gfx_LoadTex(&this->tex_left,Archive_Find(arc,"back0.tim"),0);
    Gfx_LoadTex(&this->tex_right,Archive_Find(arc,"back1.tim"),0);
    Mem_Free(arc);
    arc=IO_Read("\\SSERAFIM\\FX.ARC;1");
    Gfx_LoadTex(&this->tex_fx,Archive_Find(arc,"sf00.tim"),0);
    Mem_Free(arc);
    SF_LoadExtra(this,0,"\\CHAR\\SFYUNJ.ARC;1",sf_yunjin_pages);
    SF_LoadExtra(this,1,"\\CHAR\\SFCHAW.ARC;1",sf_chaewon_pages);
    SF_LoadExtra(this,2,"\\CHAR\\SFEUNC.ARC;1",sf_eunchae_pages);
    this->visible_mask=1;
    this->singing_mask=0;
    this->event_index=0;
    this->focus_active=false; this->focus_x=0; this->focus_y=0;
    this->zoom=FIXED_DEC(1,1); this->bop_rate=4; this->bop_intensity=0; this->bop_offset=0;
    this->cover=false; this->pulse_enabled=false; this->beautiful=false;
    this->opponent_icon_visible=false; this->ending_played=false;
    this->dark_amount=this->light_strength=0;
    this->light_timer=this->flash_timer=this->pulse_timer=this->shake_timer=0;
    this->pulse_color[0]=this->pulse_color[1]=0;
    this->pulse_duration[0]=this->pulse_duration[1]=500;
    this->pulse_intensity[0]=this->pulse_intensity[1]=0;
    this->pulse_index=0; this->player_icon=0; this->opponent_icon=2;
    this->yunjin_kick=this->kick_frame=this->kick_tick=0; this->dust_phase=0;
    for (u8 i=0;i<3;i++) { this->extra_dir[i]=0; this->extra_hold[i]=0; }
    sf_back=this;
    Gfx_SetClear(0,0,0);
    return (StageBack*)this;
}

static void SF_SetExtraDirection(Back_Sserafim *this, u8 girl, u8 direction)
{
    this->extra_dir[girl]=direction+1;
    this->extra_hold[girl]=FIXED_DEC(35,100);
}

static u8 SF_NoteAnim(u8 direction)
{
    static const u8 animations[4] = {CharAnim_Left,CharAnim_Down,CharAnim_Up,CharAnim_Right};
    return animations[direction & 3];
}

boolean Sserafim_ApplyHit(const Note *note)
{
    if (stage.stage_id != StageId_SF_1 || sf_back == NULL)
        return false;
    Back_Sserafim *this=sf_back;
    u8 direction=note->type & 3;
    boolean player_note=(note->type & NOTE_FLAG_OPPONENT)==0;
    boolean handled=false;
    if ((this->visible_mask & (1<<1)) && (((this->singing_mask>>1)&1)==player_note))
    {
        stage.opponent->set_anim(stage.opponent,SF_NoteAnim(direction));
        handled=true;
    }
    if ((this->visible_mask & (1<<4)) && (((this->singing_mask>>4)&1)==player_note))
    {
        u8 animation=SF_NoteAnim(direction);
        if (note->pad==40) animation=SFSakura_Joint_Left+direction;
        else if (note->pad==41) animation=SFSakura_BF1_Left+direction;
        else if (note->pad==42) animation=SFSakura_BF2_Left+direction;
        stage.player->set_anim(stage.player,animation);
        handled=true;
    }
    if (((this->singing_mask>>5)&1)==player_note)
    {
        u8 animation=this->beautiful ? SFGF_Beautiful_Left+direction : SF_NoteAnim(direction);
        stage.gf->set_anim(stage.gf,animation);
        handled=true;
    }
    if ((this->visible_mask & 1) && (((this->singing_mask & 1)!=0)==player_note))
    {
        SF_SetExtraDirection(this,0,direction); handled=true;
    }
    if ((this->visible_mask & 4) && ((((this->singing_mask>>2)&1)!=0)==player_note))
    {
        SF_SetExtraDirection(this,1,direction); handled=true;
    }
    if ((this->visible_mask & 8) && ((((this->singing_mask>>3)&1)!=0)==player_note))
    {
        SF_SetExtraDirection(this,2,direction); handled=true;
    }
    return handled;
}

void Sserafim_ApplyMiss(const Note *note)
{
    if (stage.stage_id != StageId_SF_1 || sf_back == NULL || (note->type & NOTE_FLAG_OPPONENT))
        return;
    u8 direction=note->type & 3;
    if (sf_back->visible_mask & (1<<4))
    {
        u8 animation=SFSakura_BaseMiss_Left+direction;
        if (note->pad==40) animation=SFSakura_JointMiss_Left+direction;
        else if (note->pad==41 || note->pad==42) animation=SFSakura_StyleMiss_Left+direction;
        stage.player->set_anim(stage.player,animation);
    }
    if ((sf_back->singing_mask>>5)&1)
    {
        u8 animation=sf_back->beautiful ? SFGF_BeautifulMiss_Left+direction : SF_NoteAnim(direction);
        stage.gf->set_anim(stage.gf,animation);
    }
}

static void SF_ProcessEvent(Back_Sserafim *this, const SserafimEvent *event)
{
    switch (event->kind)
    {
        case SFEvent_Focus:
            this->focus_active=true; this->focus_x=event->a; this->focus_y=event->b; break;
        case SFEvent_Zoom:
            this->zoom=event->a; break;
        case SFEvent_Bop:
            this->bop_rate=event->a; this->bop_intensity=event->b; this->bop_offset=event->c; break;
        case SFEvent_Show:
            this->visible_mask=event->flags; break;
        case SFEvent_Sing:
            this->singing_mask=event->flags; break;
        case SFEvent_Dark:
            this->dark_amount=event->a; break;
        case SFEvent_Lights:
            this->light_strength=event->a; this->light_timer=FIXED_DEC(event->b,1000); break;
        case SFEvent_Cover:
            this->cover=(event->flags&1)!=0; break;
        case SFEvent_Flash:
            if (!stage.reduced_flashing) this->flash_timer=FIXED_DEC(event->b,1000); break;
        case SFEvent_Pulse:
            this->pulse_enabled=(event->flags&1)!=0;
            this->pulse_color[0]=event->color0; this->pulse_color[1]=event->color1;
            this->pulse_intensity[0]=event->a; this->pulse_intensity[1]=event->c;
            this->pulse_duration[0]=event->b; this->pulse_duration[1]=event->d;
            break;
        case SFEvent_Kick:
            this->yunjin_kick=(event->flags&1)?2:1; this->kick_frame=this->kick_tick=0;
            if (event->flags&1) { this->opponent_icon_visible=true; }
            break;
        case SFEvent_Beautiful:
            this->beautiful=(event->flags&1)!=0; break;
        case SFEvent_End:
            if (!this->ending_played)
            {
                this->ending_played=true; Audio_StopXA();
                Movie_Play("\\MOVIE\\SFEND.STR;1",SSERAFIM_END_FRAMES);
            }
            break;
        case SFEvent_Vibration:
            this->shake_timer=FIXED_DEC(event->b,1000); break;
        case SFEvent_HealthIcon:
            if (event->flags) { this->opponent_icon=event->a; this->opponent_icon_visible=true; }
            else this->player_icon=event->a;
            break;
    }
}

static void SF_TickEvents(Back_Sserafim *this)
{
    if (stage.song_step < 0) return;
    while (this->event_index < SSERAFIM_EVENT_COUNT && sserafim_events[this->event_index].step <= stage.song_step)
        SF_ProcessEvent(this,&sserafim_events[this->event_index++]);
    if (this->pulse_enabled && (stage.flag&STAGE_FLAG_JUST_STEP) && (stage.song_step&3)==0)
    {
        this->pulse_index ^= 1;
        this->pulse_timer=FIXED_DEC(this->pulse_duration[this->pulse_index],1000);
    }
    if (this->shake_timer>0)
    {
        this->shake_timer-=timer_dt;
        stage.camera.tx+=FIXED_DEC(RandomRange(-3,3),1);
        stage.camera.ty+=FIXED_DEC(RandomRange(-2,2),1);
    }
    if (this->bop_rate && this->bop_intensity && (stage.flag&STAGE_FLAG_JUST_STEP) &&
        ((stage.song_step-this->bop_offset)%(this->bop_rate*4)==0))
        stage.bump=FIXED_UNIT+FIXED_DEC(this->bop_intensity,10000);
}

void Sserafim_ApplyCameraTarget(void)
{
    if (stage.stage_id != StageId_SF_1 || sf_back == NULL) return;
    SF_TickEvents(sf_back);
    if (sf_back->focus_active)
    {
        stage.camera.tx=FIXED_DEC(sf_back->focus_x,1);
        stage.camera.ty=FIXED_DEC(sf_back->focus_y,1);
    }
}

void Sserafim_ApplyCameraZoom(void)
{
    if (stage.stage_id != StageId_SF_1 || sf_back == NULL) return;
    stage.camera.zoom=sf_back->zoom;
    stage.camera.bzoom=FIXED_MUL(stage.camera.zoom,stage.bump);
}

boolean Sserafim_DrawHealthIcon(s8 side)
{
    if (stage.stage_id != StageId_SF_1 || sf_back == NULL) return false;
    if (side < 0 && !sf_back->opponent_icon_visible) return true;
    u8 icon=side<0?sf_back->opponent_icon:sf_back->player_icon;
    fixed_t hx=(128<<FIXED_SHIFT)*(10000-stage.health)/10000;
    RECT src={(s16)(3+(icon%4)*30),(s16)(131+(icon/4)*30),24,24};
    RECT_FIXED dst={hx+side*FIXED_DEC(11,1)-FIXED_DEC(12,1),(SCREEN_HEIGHT2-40)<<FIXED_SHIFT,FIXED_DEC(24,1),FIXED_DEC(24,1)};
    if (stage.downscroll) dst.y=-dst.y-dst.h;
    Stage_DrawTex(&sf_back->tex_fx,&src,&dst,FIXED_MUL(stage.bump,stage.sbump));
    return true;
}

void Sserafim_Reset(StageId id)
{
    (void)id;
}

void Sserafim_PlayIntro(StageId id)
{
    if (id != StageId_SF_1) return;
    if (!sf_session_active)
    {
        sf_session_active=true;
        Audio_StopXA();
        Movie_Play("\\MOVIE\\SFINTRO.STR;1",SSERAFIM_INTRO_FRAMES);
    }
}

void Sserafim_Exit(void)
{
    sf_session_active=false;
}
'''


SF_DEFINITION = r'''
	{ //StageId_SF_1 (SPAGHETTI)
		{Char_SFSakura_New, FIXED_DEC(175,1), FIXED_DEC(35,1)},
		{Char_SFKazuha_New, FIXED_DEC(-105,1), FIXED_DEC(8,1)},
		{Char_SFGF_New, FIXED_DEC(55,1), FIXED_DEC(-38,1)},
		Back_Sserafim_New,
		{FIXED_DEC(18,10), FIXED_DEC(19,10), FIXED_DEC(2,1)},
		9, 1, XA_Spaghetti, 0,
		StageId_SF_1, 0
	},
'''


SF_XML = r'''
			<!-- Official LE SSERAFIM collaboration -->
			<dir name = "sserafim">
				<file name = "back.arc" type = "data" source = "iso/sserafim/back.arc"/>
				<file name = "fx.arc" type = "data" source = "iso/sserafim/fx.arc"/>
			</dir>
			<dir name = "week9">
				<file name = "9.1e.cht" type = "data" source = "iso/chart/9.1e.cht"/>
				<file name = "9.1n.cht" type = "data" source = "iso/chart/9.1n.cht"/>
				<file name = "9.1h.cht" type = "data" source = "iso/chart/9.1h.cht"/>
			</dir>

'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    root = args.upstream
    (root / "src/stage/sserafim.h").write_text(SSERAFIM_H)
    (root / "src/stage/sserafim.c").write_text(SSERAFIM_C)

    replace_once(root / "Makefile", "       src/stage/weekend1.c \\\n", "       src/stage/weekend1.c \\\n       src/stage/sserafim.c \\\n", "Sserafim stage build")
    replace_once(root / "Makefile", "       src/character/darnellblazin.c \\\n", "       src/character/darnellblazin.c \\\n       src/character/sfkazuha.c \\\n       src/character/sfsakura.c \\\n       src/character/sfgf.c \\\n", "Sserafim character build")

    replace_once(root / "src/stage.h", "\tStageId_8_4, //Blazin'\n\n\tStageId_Max", "\tStageId_8_4, //Blazin'\n\n\tStageId_SF_1, //SPAGHETTI\n\n\tStageId_Max", "Sserafim StageId")
    replace_once(root / "src/audio.h", "\tXA_DarnIn, //DARNIN.XA\n\t\n\tXA_Max", "\tXA_DarnIn, //DARNIN.XA\n\tXA_Sserafim, //SPAG.XA\n\t\n\tXA_Max", "Sserafim XA file")
    replace_once(root / "src/audio.h", "\tXA_DarnellIntro,\n} XA_Track;", "\tXA_DarnellIntro,\n\tXA_Spaghetti,\n} XA_Track;", "Sserafim XA track")
    replace_once(root / "src/audio.c", '#include "main.h"\n', '#include "main.h"\n#include "sserafim_audio_generated.h"\n', "Sserafim audio header")
    replace_once(root / "src/audio.c", "\t{XA_DarnIn, XA_LENGTH(1072)}, //XA_DarnellIntro\n};", "\t{XA_DarnIn, XA_LENGTH(1072)}, //XA_DarnellIntro\n\t{XA_Sserafim, XA_LENGTH(SSERAFIM_XA_CENTISECONDS)}, //XA_Spaghetti\n};", "Sserafim XA length")
    replace_once(root / "src/audio.c", "\t\t\"\\\\MUSIC\\\\DARNIN.XA;1\", //XA_DarnIn\n", "\t\t\"\\\\MUSIC\\\\DARNIN.XA;1\", //XA_DarnIn\n\t\t\"\\\\MUSIC\\\\SPAG.XA;1\",   //XA_Sserafim\n", "Sserafim XA path")

    stage = root / "src/stage.c"
    replace_once(stage, '#include "stage/weekend1.h"\n', '#include "stage/weekend1.h"\n#include "stage/sserafim.h"\n', "Sserafim stage include")
    replace_once(stage, '#include "character/darnellblazin.h"\n', '#include "character/darnellblazin.h"\n#include "character/sfkazuha.h"\n#include "character/sfsakura.h"\n#include "character/sfgf.h"\n', "Sserafim character includes")
    replace_once(stage, "\t\t\tif (!Weekend1_ApplyHit(note))\n\t\t\t\tstage.player->set_anim", "\t\t\tif (!Weekend1_ApplyHit(note) && !Sserafim_ApplyHit(note))\n\t\t\t\tstage.player->set_anim", "Sserafim player hits")
    replace_once(stage, "\t\t\t\t\tif (!Weekend1_ApplyHit(note))\n\t\t\t\t\t\tstage.opponent->set_anim", "\t\t\t\t\tif (!Weekend1_ApplyHit(note) && !Sserafim_ApplyHit(note))\n\t\t\t\t\t\tstage.opponent->set_anim", "Sserafim opponent hits")
    replace_once(stage,
        "\t\t\t\t\t\tWeekend1_ApplyMiss(note);\n\t\t\t\t\t\tStage_MissNote();",
        "\t\t\t\t\t\tWeekend1_ApplyMiss(note);\n\t\t\t\t\t\tSserafim_ApplyMiss(note);\n\t\t\t\t\t\tStage_MissNote();",
        "Sserafim Kade miss animation")
    replace_once(stage,
        "\t\t\t\t\tWeekend1_ApplyMiss(note);\n\t\t\t\t\tStage_MissNote();",
        "\t\t\t\t\tWeekend1_ApplyMiss(note);\n\t\t\t\t\tSserafim_ApplyMiss(note);\n\t\t\t\t\tStage_MissNote();",
        "Sserafim standard miss animation")
    replace_once(stage, "\tWeekend1_Reset(id);\n\tWeekend1_PlayIntro(id, story);", "\tWeekend1_Reset(id);\n\tSserafim_Reset(id);\n\tWeekend1_PlayIntro(id, story);\n\tSserafim_PlayIntro(id);", "Sserafim load lifecycle")
    text = stage.read_text()
    text = re.sub(r"(?m)^(\s*)Weekend1_ApplyCameraTarget\(\);$", r"\1Weekend1_ApplyCameraTarget();\n\1Sserafim_ApplyCameraTarget();", text)
    text = re.sub(r"(?m)^(\s*)Weekend1_ApplyCameraZoom\(\);$", r"\1Weekend1_ApplyCameraZoom();\n\1Sserafim_ApplyCameraZoom();", text)
    stage.write_text(text)
    replace_once(stage, "\t\t\t\tWeekend1_ExitStory();\n", "\t\t\t\tWeekend1_ExitStory();\n\t\t\t\tSserafim_Exit();\n", "Sserafim exit lifecycle")
    replace_once(stage, "\t\t\tStage_DrawHealth(stage.player->health_i,    1);\n\t\t\tStage_DrawHealth(stage.opponent->health_i, -1);", "\t\t\tif (!Sserafim_DrawHealthIcon(1)) Stage_DrawHealth(stage.player->health_i, 1);\n\t\t\tif (!Sserafim_DrawHealthIcon(-1)) Stage_DrawHealth(stage.opponent->health_i, -1);", "Sserafim health icons")
    replace_once(stage, "\t\t\"DARNELL\", \"LIT UP\", \"TWO HOT\", \"BLAZIN'\",\n", "\t\t\"DARNELL\", \"LIT UP\", \"TWO HOT\", \"BLAZIN'\",\n\t\t\"SPAGHETTI\",\n", "Sserafim pause title")

    stagedefs = root / "src/stagedef_disc1.h"
    stagedefs.write_text(stagedefs.read_text().rstrip() + SF_DEFINITION)

    xml = root / "funkin.xml"
    replace_once(xml, "\t\t\t<!-- Kapi assets -->", SF_XML + "\t\t\t<!-- Kapi assets -->", "Sserafim XML stage")
    replace_once(xml, "\t\t\t\t<file name = \"darnbl.arc\" type = \"data\" source = \"iso/darnbl.arc\"/>\n", "\t\t\t\t<file name = \"darnbl.arc\" type = \"data\" source = \"iso/darnbl.arc\"/>\n\t\t\t\t<file name = \"sfkaz.arc\" type = \"data\" source = \"iso/sfkaz.arc\"/>\n\t\t\t\t<file name = \"sfsaku.arc\" type = \"data\" source = \"iso/sfsaku.arc\"/>\n\t\t\t\t<file name = \"sfgf.arc\" type = \"data\" source = \"iso/sfgf.arc\"/>\n\t\t\t\t<file name = \"sfyunj.arc\" type = \"data\" source = \"iso/sfyunj.arc\"/>\n\t\t\t\t<file name = \"sfchaw.arc\" type = \"data\" source = \"iso/sfchaw.arc\"/>\n\t\t\t\t<file name = \"sfeunc.arc\" type = \"data\" source = \"iso/sfeunc.arc\"/>\n", "Sserafim XML characters")
    replace_once(xml, "\t\t\t\t<file name = \"darnin.xa\" type = \"xa\" source = \"iso/music/darnin.xa\"/>\n", "\t\t\t\t<file name = \"darnin.xa\" type = \"xa\" source = \"iso/music/darnin.xa\"/>\n\t\t\t\t<file name = \"spag.xa\" type = \"xa\" source = \"iso/music/spag.xa\"/>\n", "Sserafim XML audio")
    replace_once(xml, "\t\t\t\t<file name = \"blazin.str\" type = \"xa\" source = \"iso/movie/blazin.str\"/>\n", "\t\t\t\t<file name = \"blazin.str\" type = \"xa\" source = \"iso/movie/blazin.str\"/>\n\t\t\t\t<file name = \"sfintro.str\" type = \"xa\" source = \"iso/movie/sfintro.str\"/>\n\t\t\t\t<file name = \"sfend.str\" type = \"xa\" source = \"iso/movie/sfend.str\"/>\n", "Sserafim XML movies")

    menu = root / "src/menu.c"
    replace_once(menu, "#define MENU_FP_SONG_COUNT 26", "#define MENU_FP_SONG_COUNT 27", "Sserafim Freeplay count")
    replace_once(menu, "\t{StageId_8_4, XA_Blazin, 6, \"BLAZIN'\", \"WEEKEND 1\", 180, 180, {3,4,5,0,0}, 2, 18},\n};", "\t{StageId_8_4, XA_Blazin, 6, \"BLAZIN'\", \"WEEKEND 1\", 180, 180, {3,4,5,0,0}, 2, 18},\n\t{StageId_SF_1, XA_Spaghetti, 0, \"SPAGHETTI\", \"SP. COLLAB 1\", 112, 112, {2,3,5,0,0}, 3, 19},\n};", "Sserafim Freeplay entry")
    replace_once(menu, "\t\t\t\t{\"8\", StageId_8_1, \"DUE DEBTS\", {\"DARNELL\", \"LIT UP\", \"TWO HOT\", \"BLAZIN'\"}},", "\t\t\t\t{\"8\", StageId_8_1, \"DUE DEBTS\", {\"DARNELL\", \"LIT UP\", \"TWO HOT\", \"BLAZIN'\"}},\n\t\t\t\t{\"9\", StageId_SF_1, \"LE SSERAFIM\", {\"SPAGHETTI\", NULL, NULL, NULL}},", "Sserafim Story entry")

    print("Official LE SSERAFIM collaboration applied additively")


if __name__ == "__main__":
    main()
