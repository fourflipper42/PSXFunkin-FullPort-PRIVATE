#!/usr/bin/env python3
"""Add the official Weekend 1 runtime without deleting legacy port content."""

from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


WEEKEND1_H = r'''#ifndef _WEEKEND1_H
#define _WEEKEND1_H

#include "../stage.h"

StageBack *Back_Weekend1_New(void);
boolean Weekend1_ApplyHit(const Note *note);
void Weekend1_ApplyMiss(const Note *note);
void Weekend1_ApplyCameraTarget(void);
void Weekend1_ApplyCameraZoom(void);
void Weekend1_Reset(StageId id);
void Weekend1_PlayIntro(StageId id, boolean story);
boolean Weekend1_BeginInGameIntro(StageId id, boolean story);
boolean Weekend1_InGameIntroTick(void);
boolean Weekend1_PlayEnding(void);
void Weekend1_ExitStory(void);
boolean Weekend1_IsStage(StageId id);
boolean Weekend1_MiddleScroll(void);

#endif
'''


WEEKEND1_C = r'''#include "weekend1.h"

#include "../mem.h"
#include "../archive.h"
#include "../audio.h"
#include "../movie.h"
#include "../random.h"
#include "../timer.h"

#include "../character/picoplayer.h"
#include "../character/nene.h"
#include "../character/darnell.h"
#include "../character/picoblazin.h"
#include "../character/darnellblazin.h"

#include "../weekend1_movies_generated.h"

typedef struct
{
    u16 step;
    s8 focus;
    s16 x, y;
} Weekend1FocusEvent;

typedef struct
{
    u16 step, duration;
    s16 zoom;
    u8 ease;
} Weekend1ZoomEvent;

typedef struct
{
    u8 tex;
    RECT src;
} Weekend1SpriteFrame;

#include "../weekend1_events_generated.h"
#include "../weekend1_fx_generated.h"

enum
{
    W1K_LightCan = 1,
    W1K_KickCan = 2,
    W1K_CockGun = 3,
    W1K_KneeCan = 4,
    W1K_FireGun = 5,
    W1K_BlockHigh = 10,
    W1K_PunchHighBlocked = 11,
    W1K_PunchLowDodged = 12,
    W1K_DodgeLow = 13,
    W1K_BlockSpin = 14,
    W1K_PunchHigh = 15,
    W1K_HitHigh = 16,
    W1K_DodgeHigh = 17,
    W1K_DarnellUpperPrep = 18,
    W1K_DarnellUpper = 19,
    W1K_HitLow = 20,
    W1K_PicoUpperPrep = 21,
    W1K_PicoUpper = 22,
    W1K_BlockLow = 23,
    W1K_PunchLow = 24,
    W1K_PunchLowSpin = 25,
    W1K_Fakeout = 26,
    W1K_Taunt = 27,
    W1K_Idle = 28,
    W1K_PunchLowBlocked = 29,
    W1K_PunchHighSpin = 30,
};

typedef struct
{
    StageBack back;
    Gfx_Tex tex_left, tex_right;
    Gfx_Tex tex_fx[4];
    boolean blazin;
    boolean lights_stop;
    u8 traffic_frame, traffic_tick;
    s16 last_light_beat;
    u8 light_interval;
    boolean car_active[2];
    u8 car_variant[2];
    fixed_t car_progress[2], car_speed[2];
    fixed_t lightning_timer;
    u8 lightning_frame, lightning_tick;
    s16 lightning_x;
    u16 rain_phase;
} Back_Weekend1;

static boolean weekend1_story_active = false;
static u8 weekend1_movies_seen = 0;
static s16 weekend1_gun_cock_step = -1000;
static boolean weekend1_uppercut_ready = false;
static boolean weekend1_cant_uppercut = false;
static boolean weekend1_fakeout_active = false;
static boolean weekend1_pico_high_alt = false;
static boolean weekend1_pico_low_alt = false;
static boolean weekend1_darnell_high_alt = false;
static boolean weekend1_darnell_low_alt = false;
static fixed_t weekend1_intro_time = 0;
static u16 weekend1_intro_events = 0;
static fixed_t weekend1_ending_time = 0;
static u8 weekend1_ending_events = 0;
static boolean weekend1_ending_active = false;

boolean Weekend1_IsStage(StageId id)
{
    return id >= StageId_8_1 && id <= StageId_8_4;
}

boolean Weekend1_MiddleScroll(void)
{
    return stage.stage_id == StageId_8_4;
}

void Weekend1_Reset(StageId id)
{
    if (!Weekend1_IsStage(id))
        return;
    weekend1_gun_cock_step = -1000;
    weekend1_uppercut_ready = false;
    weekend1_cant_uppercut = false;
    weekend1_fakeout_active = false;
    weekend1_pico_high_alt = false;
    weekend1_pico_low_alt = false;
    weekend1_darnell_high_alt = false;
    weekend1_darnell_low_alt = false;
    weekend1_ending_time = 0;
    weekend1_ending_events = 0;
    weekend1_ending_active = false;
}

static void W1_DrawSprite(Back_Weekend1 *this, const Weekend1SpriteFrame *frame,
                          fixed_t x, fixed_t y, fixed_t width, fixed_t height)
{
    RECT_FIXED dst = {x - stage.camera.x, y - stage.camera.y, width, height};
    Stage_DrawTex(&this->tex_fx[frame->tex], &frame->src, &dst, stage.camera.bzoom);
}

static void W1_SpawnCar(Back_Weekend1 *this, u8 lane)
{
    this->car_active[lane] = true;
    this->car_variant[lane] = RandomRange(0, W1_STREET_CAR_COUNT - 1);
    this->car_progress[lane] = 0;
    this->car_speed[lane] = FIXED_DEC(RandomRange(42, 80),100);
}

static void W1_UpdateStreet(Back_Weekend1 *this)
{
    if ((stage.flag & STAGE_FLAG_JUST_STEP) && (stage.song_step & 3) == 0 && stage.song_step >= 0)
    {
        s16 beat = stage.song_step >> 2;
        if (beat == this->last_light_beat + this->light_interval)
        {
            this->last_light_beat = beat;
            this->lights_stop = !this->lights_stop;
            this->light_interval = this->lights_stop ? 20 : 30;
            this->traffic_frame = this->traffic_tick = 0;
        }
        if (beat != this->last_light_beat + this->light_interval)
        {
            if (!this->car_active[0] && RandomRange(0,99) < 10)
                W1_SpawnCar(this,0);
            if (!this->lights_stop && !this->car_active[1] && RandomRange(0,99) < 10)
                W1_SpawnCar(this,1);
        }
    }
    if (++this->traffic_tick >= 3)
    {
        this->traffic_tick = 0;
        if (this->traffic_frame + 1 < W1_STREET_GREEN_COUNT)
            this->traffic_frame++;
    }
    for (u8 i=0;i<2;i++)
    {
        if (!this->car_active[i]) continue;
        this->car_progress[i] += FIXED_MUL(timer_dt,this->car_speed[i]);
        if (this->car_progress[i] >= FIXED_UNIT)
        {
            this->car_progress[i] = FIXED_UNIT;
            this->car_active[i] = false;
        }
    }
}

static void W1_DrawStreet(Back_Weekend1 *this)
{
    W1_UpdateStreet(this);
    const Weekend1SpriteFrame *traffic = this->lights_stop ? w1_street_red : w1_street_green;
    W1_DrawSprite(this,&traffic[this->traffic_frame],FIXED_DEC(58,1),FIXED_DEC(-148,1),FIXED_DEC(128,1),FIXED_DEC(128,1));
    for (u8 i=0;i<2;i++)
    {
        if (!this->car_active[i]) continue;
        fixed_t t=this->car_progress[i];
        fixed_t x=FIXED_DEC(-250,1)+FIXED_MUL(FIXED_DEC(600,1),t);
        if (i) x=FIXED_DEC(350,1)-FIXED_MUL(FIXED_DEC(600,1),t);
        fixed_t arch=FIXED_MUL(FIXED_MUL(t,FIXED_UNIT-t),FIXED_DEC(72,1));
        fixed_t y=FIXED_DEC(-35,1)-arch;
        W1_DrawSprite(this,&w1_street_car[this->car_variant[i]],x,y,FIXED_DEC(128,1),FIXED_DEC(128,1));
    }
}

static void W1_UpdateLightning(Back_Weekend1 *this)
{
    if (this->lightning_frame < W1_BLAZIN_LIGHTNING_COUNT)
    {
        if (++this->lightning_tick >= 2)
        {
            this->lightning_tick=0;
            this->lightning_frame++;
        }
        return;
    }
    this->lightning_timer -= timer_dt;
    if (this->lightning_timer <= 0)
    {
        this->lightning_timer=RandomRange(FIXED_DEC(7,1),FIXED_DEC(15,1));
        this->lightning_frame=this->lightning_tick=0;
        this->lightning_x=RandomRange(-120,150);
    }
}

static void Back_Weekend1_DrawFG(StageBack *back)
{
    Back_Weekend1 *this=(Back_Weekend1*)back;
    u8 drops=this->blazin ? 20 : (stage.stage_id==StageId_8_3 ? 14 : (stage.stage_id==StageId_8_2 ? 9 : 5));
    this->rain_phase += this->blazin ? 5 : 3;
    for (u8 i=0;i<drops;i++)
    {
        RECT drop={(s16)(((i*53+this->rain_phase*2)%350)-15),(s16)(((i*79+this->rain_phase*5)%250)-8),1,(s16)(3+(i&3))};
        Gfx_DrawRect(&drop,this->blazin ? 0x58 : 0x38,this->blazin ? 0x68 : 0x50,this->blazin ? 0x78 : 0x68);
    }
}

static void Back_Weekend1_DrawBG(StageBack *back)
{
    Back_Weekend1 *this = (Back_Weekend1*)back;
    if (this->blazin)
    {
        W1_UpdateLightning(this);
        if (this->lightning_frame < W1_BLAZIN_LIGHTNING_COUNT)
            W1_DrawSprite(this,&w1_blazin_lightning[this->lightning_frame],FIXED_DEC(this->lightning_x,1),FIXED_DEC(-150,1),FIXED_DEC(128,1),FIXED_DEC(128,1));
    }
    else
        W1_DrawStreet(this);

    const RECT src = {0, 0, 256, 240};
    RECT_FIXED dst = {FIXED_DEC(-256,1)-stage.camera.x,FIXED_DEC(-120,1)-stage.camera.y,FIXED_DEC(256,1),FIXED_DEC(240,1)};
    Stage_DrawTex(&this->tex_left,&src,&dst,stage.camera.bzoom);
    dst.x += FIXED_DEC(256,1);
    Stage_DrawTex(&this->tex_right,&src,&dst,stage.camera.bzoom);
}

static void Back_Weekend1_Free(StageBack *back)
{
    Mem_Free(back);
}

StageBack *Back_Weekend1_New(void)
{
    Back_Weekend1 *this = (Back_Weekend1*)Mem_Alloc(sizeof(Back_Weekend1));
    if (this == NULL)
        return NULL;
    this->back.draw_fg = Back_Weekend1_DrawFG;
    this->back.draw_md = NULL;
    this->back.draw_bg = Back_Weekend1_DrawBG;
    this->back.free = Back_Weekend1_Free;
    this->blazin = stage.stage_id == StageId_8_4;
    const char *path = this->blazin ? "\\WEEK8\\BLAZIN.ARC;1" : "\\WEEK8\\BACK.ARC;1";
    IO_Data arc = IO_Read(path);
    Gfx_LoadTex(&this->tex_left, Archive_Find(arc, "back0.tim"), 0);
    Gfx_LoadTex(&this->tex_right, Archive_Find(arc, "back1.tim"), 0);
    Mem_Free(arc);
    arc = IO_Read(this->blazin ? "\\WEEK8\\BLAZINFX.ARC;1" : "\\WEEK8\\STREETFX.ARC;1");
    static const char *const fx_names[] = {"fx00.tim","fx01.tim","fx02.tim","fx03.tim"};
    u8 fx_count = this->blazin ? 4 : 3;
    for (u8 i=0;i<fx_count;i++) Gfx_LoadTex(&this->tex_fx[i],Archive_Find(arc,fx_names[i]),0);
    Mem_Free(arc);
    this->lights_stop=false; this->traffic_frame=W1_STREET_GREEN_COUNT-1; this->traffic_tick=0;
    this->last_light_beat=0; this->light_interval=8;
    this->car_active[0]=this->car_active[1]=false;
    this->lightning_timer=FIXED_DEC(3,1); this->lightning_frame=W1_BLAZIN_LIGHTNING_COUNT; this->lightning_tick=0;
    this->rain_phase=0;
    Gfx_SetClear(0, 0, 0);
    return (StageBack*)this;
}

static void W1_Set(Character *character, u8 animation)
{
    character->set_anim(character, animation);
}

static void W1_PicoFight(u8 kind, boolean missed)
{
    if (missed)
    {
        switch (kind)
        {
            case W1K_PunchLow: case W1K_PunchLowBlocked: case W1K_PunchLowDodged:
            case W1K_BlockLow: case W1K_DodgeLow: case W1K_HitLow:
                W1_Set(stage.player, PicoBlazin_Hit_Low); return;
            case W1K_PunchLowSpin: case W1K_BlockSpin: case W1K_PunchHighSpin:
                W1_Set(stage.player, PicoBlazin_Hit_Spin); return;
            case W1K_PicoUpperPrep:
                W1_Set(stage.player, PicoBlazin_Punch_High_1); return;
            case W1K_PicoUpper: case W1K_DarnellUpper:
                W1_Set(stage.player, PicoBlazin_Uppercut_Hit); return;
            default:
                W1_Set(stage.player, PicoBlazin_Hit_High); return;
        }
    }
    switch (kind)
    {
        case W1K_BlockHigh: case W1K_BlockLow: case W1K_BlockSpin:
            W1_Set(stage.player, PicoBlazin_Block); break;
        case W1K_DodgeHigh: case W1K_DodgeLow:
            W1_Set(stage.player, PicoBlazin_Dodge); break;
        case W1K_PunchHigh: case W1K_PunchHighBlocked: case W1K_PunchHighSpin:
            W1_Set(stage.player, weekend1_pico_high_alt ? PicoBlazin_Punch_High_2 : PicoBlazin_Punch_High_1);
            weekend1_pico_high_alt = !weekend1_pico_high_alt; break;
        case W1K_PunchLow: case W1K_PunchLowBlocked: case W1K_PunchLowDodged: case W1K_PunchLowSpin:
            W1_Set(stage.player, weekend1_pico_low_alt ? PicoBlazin_Punch_Low_2 : PicoBlazin_Punch_Low_1);
            weekend1_pico_low_alt = !weekend1_pico_low_alt; break;
        case W1K_HitHigh: case W1K_DarnellUpper:
            W1_Set(stage.player, PicoBlazin_Hit_High); break;
        case W1K_HitLow:
            W1_Set(stage.player, PicoBlazin_Hit_Low); break;
        case W1K_DarnellUpperPrep: case W1K_Idle:
            W1_Set(stage.player, CharAnim_Idle); break;
        case W1K_PicoUpperPrep:
            W1_Set(stage.player, PicoBlazin_Uppercut_Prep); break;
        case W1K_PicoUpper:
            W1_Set(stage.player, PicoBlazin_Uppercut_Punch); break;
        case W1K_Fakeout:
            W1_Set(stage.player, PicoBlazin_Fake_Hit); break;
        case W1K_Taunt:
            W1_Set(stage.player, PicoBlazin_Taunt); break;
        default: break;
    }
}

static void W1_DarnellFight(u8 kind, boolean missed)
{
    if (missed)
    {
        switch (kind)
        {
            case W1K_PunchLow: case W1K_PunchLowBlocked: case W1K_PunchLowDodged:
                W1_Set(stage.opponent, DarnellBlazin_Punch_Low_1); return;
            case W1K_PunchHigh: case W1K_PunchHighBlocked: case W1K_BlockHigh:
            case W1K_DodgeHigh: case W1K_HitHigh:
                W1_Set(stage.opponent, DarnellBlazin_Punch_High_1); return;
            case W1K_BlockLow: case W1K_DodgeLow: case W1K_HitLow:
                W1_Set(stage.opponent, DarnellBlazin_Punch_Low_1); return;
            case W1K_PicoUpper:
                W1_Set(stage.opponent, DarnellBlazin_Dodge); return;
            case W1K_PicoUpperPrep:
                W1_Set(stage.opponent, DarnellBlazin_Hit_High); return;
            default: break;
        }
    }
    switch (kind)
    {
        case W1K_PunchLow:
            W1_Set(stage.opponent, DarnellBlazin_Hit_Low); break;
        case W1K_PunchLowBlocked: case W1K_PunchHighBlocked:
            W1_Set(stage.opponent, DarnellBlazin_Block); break;
        case W1K_PunchLowDodged:
            W1_Set(stage.opponent, DarnellBlazin_Dodge); break;
        case W1K_PunchLowSpin: case W1K_PunchHighSpin: case W1K_BlockSpin:
            W1_Set(stage.opponent, DarnellBlazin_Hit_Spin); break;
        case W1K_PunchHigh:
            W1_Set(stage.opponent, DarnellBlazin_Hit_High); break;
        case W1K_BlockHigh: case W1K_HitHigh: case W1K_DodgeHigh:
            W1_Set(stage.opponent, weekend1_darnell_high_alt ? DarnellBlazin_Punch_High_2 : DarnellBlazin_Punch_High_1);
            weekend1_darnell_high_alt = !weekend1_darnell_high_alt; break;
        case W1K_BlockLow: case W1K_HitLow: case W1K_DodgeLow:
            W1_Set(stage.opponent, weekend1_darnell_low_alt ? DarnellBlazin_Punch_Low_2 : DarnellBlazin_Punch_Low_1);
            weekend1_darnell_low_alt = !weekend1_darnell_low_alt; break;
        case W1K_PicoUpper:
            W1_Set(stage.opponent, DarnellBlazin_Uppercut_Hit); break;
        case W1K_DarnellUpperPrep:
            W1_Set(stage.opponent, DarnellBlazin_Uppercut_Prep); break;
        case W1K_DarnellUpper:
            W1_Set(stage.opponent, DarnellBlazin_Uppercut_Punch); break;
        case W1K_Idle:
            W1_Set(stage.opponent, CharAnim_Idle); break;
        case W1K_Fakeout:
            W1_Set(stage.opponent, DarnellBlazin_Cringe); break;
        case W1K_Taunt:
            W1_Set(stage.opponent, DarnellBlazin_Pissed); break;
        default: break;
    }
}

boolean Weekend1_ApplyHit(const Note *note)
{
    if (note->type & NOTE_FLAG_SUSTAIN)
        return false;
    if (stage.stage_id == StageId_8_3)
    {
        switch (note->pad)
        {
            case W1K_CockGun:
                weekend1_gun_cock_step = stage.song_step;
                W1_Set(stage.player, PicoPlayer_GunReload);
                return true;
            case W1K_FireGun:
                if (stage.song_step - weekend1_gun_cock_step <= 8)
                    W1_Set(stage.player, PicoPlayer_Shoot);
                else
                {
                    W1_Set(stage.player, PicoPlayer_Hit);
                    stage.health -= 5000;
                }
                weekend1_gun_cock_step = -1000;
                return true;
            case W1K_LightCan: W1_Set(stage.opponent, Darnell_LightCan); return true;
            case W1K_KickCan: W1_Set(stage.opponent, Darnell_KickUp); return true;
            case W1K_KneeCan: W1_Set(stage.opponent, Darnell_KneeForward); return true;
            default: return false;
        }
    }
    if (stage.stage_id == StageId_8_4 && note->pad >= W1K_BlockHigh)
    {
        if (!(note->type & NOTE_FLAG_OPPONENT))
        {
            if (weekend1_cant_uppercut)
            {
                W1_Set(stage.player, PicoBlazin_Block);
                W1_Set(stage.opponent, DarnellBlazin_Punch_High_1);
                weekend1_cant_uppercut = false;
                weekend1_uppercut_ready = false;
                return true;
            }

            fixed_t offset = stage.note_scroll - ((fixed_t)note->pos << FIXED_SHIFT);
            if (offset < 0) offset = -offset;
            fixed_t poor_limit = stage.kade ? stage.late_safe * 54 / 100 : stage.late_safe * 3 / 4;
            if (stage.health <= 6000 && offset > poor_limit && RandomRange(0, 99) < 30)
            {
                W1_Set(stage.player, PicoBlazin_Punch_High_1);
                W1_Set(stage.opponent, DarnellBlazin_Uppercut_Prep);
                weekend1_uppercut_ready = true;
                return true;
            }
            weekend1_uppercut_ready = false;
        }

        if (note->pad == W1K_Taunt && !weekend1_fakeout_active)
        {
            W1_Set(stage.player, CharAnim_Idle);
            W1_Set(stage.opponent, CharAnim_Idle);
            return true;
        }
        W1_PicoFight(note->pad, false);
        W1_DarnellFight(note->pad, false);
        weekend1_fakeout_active = note->pad == W1K_Fakeout;
        return true;
    }
    return false;
}

void Weekend1_ApplyMiss(const Note *note)
{
    if (stage.stage_id == StageId_8_3 && !(note->type & NOTE_FLAG_SUSTAIN))
    {
        if (note->pad == W1K_CockGun)
            weekend1_gun_cock_step = -1000;
        else if (note->pad == W1K_FireGun)
        {
            weekend1_gun_cock_step = -1000;
            W1_Set(stage.player, PicoPlayer_Hit);
            stage.health -= 4525;
        }
        return;
    }
    if (stage.stage_id == StageId_8_4 && !(note->type & NOTE_FLAG_SUSTAIN) && note->pad >= W1K_BlockHigh)
    {
        if (weekend1_uppercut_ready)
        {
            W1_Set(stage.player, PicoBlazin_Uppercut_Hit);
            W1_Set(stage.opponent, DarnellBlazin_Uppercut_Punch);
            weekend1_uppercut_ready = false;
            return;
        }
        if (weekend1_cant_uppercut)
        {
            W1_Set(stage.player, PicoBlazin_Hit_High);
            W1_Set(stage.opponent, DarnellBlazin_Punch_High_1);
            weekend1_cant_uppercut = false;
            return;
        }
        W1_PicoFight(note->pad, true);
        W1_DarnellFight(note->pad, true);
        if (note->pad == W1K_PicoUpperPrep)
            weekend1_cant_uppercut = true;
        weekend1_fakeout_active = note->pad == W1K_Fakeout;
    }
}

static void W1_SelectEvents(const Weekend1FocusEvent **focus, u16 *focus_count,
                            const Weekend1ZoomEvent **zoom, u16 *zoom_count)
{
    *focus = NULL; *focus_count = 0; *zoom = NULL; *zoom_count = 0;
    switch (stage.stage_id)
    {
        case StageId_8_1:
            if (stage.stage_diff >= StageDiff_Erect)
            {
                *focus = w1_focus_1_erect; *focus_count = W1_FOCUS_1_ERECT_COUNT;
                *zoom = w1_zoom_1_erect; *zoom_count = W1_ZOOM_1_ERECT_COUNT;
            }
            else
            {
                *focus = w1_focus_1; *focus_count = W1_FOCUS_1_COUNT;
                *zoom = w1_zoom_1; *zoom_count = W1_ZOOM_1_COUNT;
            }
            break;
        case StageId_8_2:
            *focus = w1_focus_2; *focus_count = W1_FOCUS_2_COUNT;
            *zoom = w1_zoom_2; *zoom_count = W1_ZOOM_2_COUNT;
            break;
        case StageId_8_3:
            *focus = w1_focus_3; *focus_count = W1_FOCUS_3_COUNT;
            *zoom = w1_zoom_3; *zoom_count = W1_ZOOM_3_COUNT;
            break;
        case StageId_8_4:
            *focus = w1_focus_4; *focus_count = W1_FOCUS_4_COUNT;
            *zoom = w1_zoom_4; *zoom_count = W1_ZOOM_4_COUNT;
            break;
        default: break;
    }
}

void Weekend1_ApplyCameraTarget(void)
{
    if (!Weekend1_IsStage(stage.stage_id) || stage.song_step < 0)
        return;
    const Weekend1FocusEvent *focus;
    const Weekend1ZoomEvent *zoom;
    u16 focus_count, zoom_count;
    W1_SelectEvents(&focus, &focus_count, &zoom, &zoom_count);
    (void)zoom; (void)zoom_count;
    const Weekend1FocusEvent *active = NULL;
    for (u16 i = 0; i < focus_count && focus[i].step <= stage.song_step; i++)
        active = &focus[i];
    if (active != NULL)
    {
        Character *target = active->focus == 0 ? stage.player : (active->focus == 1 ? stage.opponent : stage.gf);
        Stage_FocusCharacter(target, FIXED_UNIT / 24);
        stage.camera.tx += FIXED_DEC(active->x,1);
        stage.camera.ty += FIXED_DEC(active->y,1);
    }
    stage.camera.tz = FIXED_DEC(77,100);
}

static fixed_t W1_Ease(u8 ease, fixed_t t)
{
    if (t <= 0) return 0;
    if (t >= FIXED_UNIT) return FIXED_UNIT;
    if (ease == 1)
    {
        if (t < FIXED_UNIT / 2)
            return FIXED_MUL(FIXED_DEC(2,1), FIXED_MUL(t,t));
        fixed_t inv = FIXED_UNIT - t;
        return FIXED_UNIT - FIXED_MUL(FIXED_DEC(2,1), FIXED_MUL(inv,inv));
    }
    if (ease == 2)
    {
        static const s16 elastic[17] = {0,1,-1,-5,12,19,-85,-37,512,1061,1109,1005,1012,1029,1025,1023,1024};
        return elastic[(t * 16) >> FIXED_SHIFT];
    }
    return t;
}

void Weekend1_ApplyCameraZoom(void)
{
    if (!Weekend1_IsStage(stage.stage_id))
        return;
    fixed_t value = FIXED_DEC(77,100);
    if (stage.song_step >= 0)
    {
        const Weekend1FocusEvent *focus;
        const Weekend1ZoomEvent *zoom;
        u16 focus_count, zoom_count;
        W1_SelectEvents(&focus, &focus_count, &zoom, &zoom_count);
        (void)focus; (void)focus_count;
        fixed_t previous = value;
        for (u16 i = 0; i < zoom_count && zoom[i].step <= stage.song_step; i++)
        {
            const Weekend1ZoomEvent *event = &zoom[i];
            fixed_t target = event->zoom;
            if (event->duration == 0 || stage.song_step >= event->step + event->duration)
                value = target;
            else
            {
                fixed_t t = FIXED_DEC(stage.song_step - event->step, event->duration);
                fixed_t eased = W1_Ease(event->ease, t);
                value = previous + FIXED_MUL(target - previous, eased);
            }
            previous = target;
        }
    }
    stage.camera.zoom = value;
    stage.camera.bzoom = FIXED_MUL(stage.camera.zoom, stage.bump);
}

boolean Weekend1_BeginInGameIntro(StageId id, boolean story)
{
    if (!story || id != StageId_8_1 || (weekend1_movies_seen & 8))
        return false;
    weekend1_movies_seen |= 8;
    weekend1_intro_time = 0;
    weekend1_intro_events = 0;
    W1_Set(stage.player, PicoPlayer_PissedOff);
    Stage_FocusCharacter(stage.player, 0);
    stage.camera.x = stage.camera.tx;
    stage.camera.y = stage.camera.ty;
    stage.camera.zoom = stage.camera.bzoom = FIXED_DEC(13,10);
    Audio_PlayXA_Track(XA_DarnellIntro,0x40,0,false);
    Audio_WaitPlayXA();
    Timer_Reset();
    return true;
}

static void W1_IntroEvent(u8 event)
{
    u16 bit = 1u << event;
    if (weekend1_intro_events & bit) return;
    weekend1_intro_events |= bit;
    switch (event)
    {
        case 0: Stage_FocusCharacter(stage.opponent,FIXED_UNIT/24); stage.camera.zoom=stage.camera.bzoom=FIXED_DEC(66,100); break;
        case 1: W1_Set(stage.opponent,Darnell_LightCan); break;
        case 2: W1_Set(stage.player,PicoPlayer_GunReload); break;
        case 3: W1_Set(stage.opponent,Darnell_KickUp); break;
        case 4: W1_Set(stage.opponent,Darnell_KneeForward); break;
        case 5: W1_Set(stage.player,PicoPlayer_Shoot); break;
        case 6: W1_Set(stage.opponent,Darnell_Laugh); break;
        case 7: W1_Set(stage.gf,Nene_Laugh); break;
        case 8: Stage_FocusCharacter(stage.opponent,FIXED_UNIT/24); stage.camera.zoom=stage.camera.bzoom=FIXED_DEC(77,100); break;
    }
}

boolean Weekend1_InGameIntroTick(void)
{
    weekend1_intro_time += timer_dt;
    if (weekend1_intro_time >= FIXED_DEC(2,1)) W1_IntroEvent(0);
    if (weekend1_intro_time >= FIXED_DEC(5,1)) W1_IntroEvent(1);
    if (weekend1_intro_time >= FIXED_DEC(6,1)) W1_IntroEvent(2);
    if (weekend1_intro_time >= FIXED_DEC(64,10)) W1_IntroEvent(3);
    if (weekend1_intro_time >= FIXED_DEC(69,10)) W1_IntroEvent(4);
    if (weekend1_intro_time >= FIXED_DEC(71,10)) W1_IntroEvent(5);
    if (weekend1_intro_time >= FIXED_DEC(79,10)) W1_IntroEvent(6);
    if (weekend1_intro_time >= FIXED_DEC(82,10)) W1_IntroEvent(7);
    if (weekend1_intro_time >= FIXED_DEC(10,1)) W1_IntroEvent(8);
    Stage_ScrollCamera();
    if (weekend1_intro_time < FIXED_DEC(107,10) && !(pad_state.press & PAD_START))
        return true;
    Audio_StopXA();
    return false;
}

void Weekend1_PlayIntro(StageId id, boolean story)
{
    if (!story || !Weekend1_IsStage(id))
        return;
    if (!weekend1_story_active)
    {
        weekend1_story_active = true;
        weekend1_movies_seen = 0;
    }
    u8 bit = 0;
    const char *path = NULL;
    unsigned long frames = 0;
    if (id == StageId_8_1) { bit = 1; path = "\\MOVIE\\DARNELL.STR;1"; frames = W1_DARNELL_FRAMES; }
    if (path == NULL || (weekend1_movies_seen & bit))
        return;
    Audio_StopXA();
    Movie_Play(path, frames);
    weekend1_movies_seen |= bit;
}

static void W1_EndingEvent(u8 index)
{
    u8 mask = 1 << index;
    if (weekend1_ending_events & mask)
        return;
    weekend1_ending_events |= mask;
    switch (index)
    {
        case 0:
            stage.camera.tx = FIXED_DEC(8,1);
            stage.camera.ty = FIXED_DEC(-28,1);
            stage.camera.tz = FIXED_DEC(24,10);
            stage.camera.td = FIXED_DEC(3,100);
            break;
        case 1:
            W1_Set(stage.player, PicoPlayer_PissedOff);
            break;
        case 2:
            W1_Set(stage.opponent, Darnell_Pissed);
            break;
    }
}

boolean Weekend1_PlayEnding(void)
{
    if (!stage.story)
        return false;

    if (stage.stage_id == StageId_8_3 && !(weekend1_movies_seen & 2))
    {
        if (!weekend1_ending_active)
        {
            weekend1_ending_active = true;
            weekend1_ending_time = 0;
            weekend1_ending_events = 0;
            Audio_StopXA();
        }

        weekend1_ending_time += timer_dt;
        if (weekend1_ending_time >= FIXED_DEC(1,1)) W1_EndingEvent(0);
        if (weekend1_ending_time >= FIXED_DEC(2,1)) W1_EndingEvent(1);
        if (weekend1_ending_time >= FIXED_DEC(25,10)) W1_EndingEvent(2);
        Stage_ScrollCamera();

        if (weekend1_ending_time < FIXED_DEC(6,1))
            return true;

        Movie_Play("\\MOVIE\\2HOT.STR;1", W1_2HOT_FRAMES);
        weekend1_movies_seen |= 2;
        weekend1_ending_active = false;
        return false;
    }

    if (stage.stage_id == StageId_8_4 && !(weekend1_movies_seen & 4))
    {
        Audio_StopXA();
        Movie_Play("\\MOVIE\\BLAZIN.STR;1", W1_BLAZIN_FRAMES);
        weekend1_movies_seen |= 4;
    }
    return false;
}

void Weekend1_ExitStory(void)
{
    weekend1_story_active = false;
    weekend1_movies_seen = 0;
}
'''


WEEK8_DEFS = r'''
	{ //StageId_8_1 (Darnell)
		{Char_PicoPlayer_New, FIXED_DEC(154,1), FIXED_DEC(17,1)},
		{Char_Darnell_New, FIXED_DEC(-117,1), FIXED_DEC(35,1)},
		{Char_Nene_New, FIXED_DEC(0,1), FIXED_DEC(-11,1)},
		Back_Weekend1_New,
		{FIXED_DEC(2,1), FIXED_DEC(2,1), FIXED_DEC(24,10)},
		8, 1, XA_Darnell, 0,
		StageId_8_2, STAGE_LOAD_FLAG
	},
	{ //StageId_8_2 (Lit Up)
		{Char_PicoPlayer_New, FIXED_DEC(154,1), FIXED_DEC(17,1)},
		{Char_Darnell_New, FIXED_DEC(-117,1), FIXED_DEC(35,1)},
		{Char_Nene_New, FIXED_DEC(0,1), FIXED_DEC(-11,1)},
		Back_Weekend1_New,
		{FIXED_DEC(24,10), FIXED_DEC(24,10), FIXED_DEC(24,10)},
		8, 2, XA_LitUp, 2,
		StageId_8_3, 0
	},
	{ //StageId_8_3 (2Hot)
		{Char_PicoPlayer_New, FIXED_DEC(154,1), FIXED_DEC(17,1)},
		{Char_Darnell_New, FIXED_DEC(-117,1), FIXED_DEC(35,1)},
		{Char_Nene_New, FIXED_DEC(0,1), FIXED_DEC(-11,1)},
		Back_Weekend1_New,
		{FIXED_DEC(27,10), FIXED_DEC(27,10), FIXED_DEC(28,10)},
		8, 3, XA_2Hot, 4,
		StageId_8_4, 0
	},
	{ //StageId_8_4 (Blazin')
		{Char_PicoBlazin_New, FIXED_DEC(60,1), FIXED_DEC(25,1)},
		{Char_DarnellBlazin_New, FIXED_DEC(-60,1), FIXED_DEC(25,1)},
		{Char_Nene_New, FIXED_DEC(0,1), FIXED_DEC(-70,1)},
		Back_Weekend1_New,
		{FIXED_DEC(2,1), FIXED_DEC(24,10), FIXED_DEC(32,10)},
		8, 4, XA_Blazin, 6,
		StageId_8_4, 0
	},
'''


WEEK8_XML = r'''
			<!-- Official Weekend 1 assets -->
			<dir name = "week8">
				<file name = "back.arc" type = "data" source = "iso/week8/back.arc"/>
				<file name = "blazin.arc" type = "data" source = "iso/week8/blazin.arc"/>
				<file name = "streetfx.arc" type = "data" source = "iso/week8/streetfx.arc"/>
				<file name = "blazinfx.arc" type = "data" source = "iso/week8/blazinfx.arc"/>
				<file name = "8.1e.cht" type = "data" source = "iso/chart/8.1e.cht"/>
				<file name = "8.1n.cht" type = "data" source = "iso/chart/8.1n.cht"/>
				<file name = "8.1h.cht" type = "data" source = "iso/chart/8.1h.cht"/>
				<file name = "8.1r.cht" type = "data" source = "iso/chart/8.1r.cht"/>
				<file name = "8.1m.cht" type = "data" source = "iso/chart/8.1m.cht"/>
				<file name = "8.2e.cht" type = "data" source = "iso/chart/8.2e.cht"/>
				<file name = "8.2n.cht" type = "data" source = "iso/chart/8.2n.cht"/>
				<file name = "8.2h.cht" type = "data" source = "iso/chart/8.2h.cht"/>
				<file name = "8.3e.cht" type = "data" source = "iso/chart/8.3e.cht"/>
				<file name = "8.3n.cht" type = "data" source = "iso/chart/8.3n.cht"/>
				<file name = "8.3h.cht" type = "data" source = "iso/chart/8.3h.cht"/>
				<file name = "8.4e.cht" type = "data" source = "iso/chart/8.4e.cht"/>
				<file name = "8.4n.cht" type = "data" source = "iso/chart/8.4n.cht"/>
				<file name = "8.4h.cht" type = "data" source = "iso/chart/8.4h.cht"/>
			</dir>

'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    root = args.upstream

    (root / "src/stage/weekend1.h").write_text(WEEKEND1_H)
    (root / "src/stage/weekend1.c").write_text(WEEKEND1_C)

    replace_once(root / "Makefile", "       src/stage/week7.c \\\n", "       src/stage/week7.c \\\n       src/stage/weekend1.c \\\n", "Makefile Weekend stage")
    replace_once(root / "Makefile", "       src/character/pico.c \\\n", "       src/character/pico.c \\\n       src/character/picoplayer.c \\\n       src/character/nene.c \\\n       src/character/darnell.c \\\n       src/character/picoblazin.c \\\n       src/character/darnellblazin.c \\\n", "Makefile Weekend characters")

    replace_once(root / "src/stage.h", "\tStageId_Clwn_4, //Expurgation\n\t\n\tStageId_Max", "\tStageId_Clwn_4, //Expurgation\n\n\tStageId_8_1, //Darnell\n\tStageId_8_2, //Lit Up\n\tStageId_8_3, //2Hot\n\tStageId_8_4, //Blazin'\n\n\tStageId_Max", "StageId Weekend append")
    replace_once(root / "src/stage.h", "\t\tStageState_Play, //Game is playing as normal\n\t\tStageState_Pause,", "\t\tStageState_Play, //Game is playing as normal\n\t\tStageState_WeekendIntro, //Darnell's official in-engine can cutscene\n\t\tStageState_Pause,", "Weekend in-game cutscene state")

    replace_once(root / "src/audio.h", "\tXA_ClwnB,  //CLWNB.XA\n\t\n\tXA_Max", "\tXA_ClwnB,  //CLWNB.XA\n\tXA_Week8,  //WEEK8.XA\n\tXA_DarnIn, //DARNIN.XA\n\t\n\tXA_Max", "XA file Weekend")
    replace_once(root / "src/audio.h", "\tXA_Expurgation, //Expurgation\n} XA_Track;", "\tXA_Expurgation, //Expurgation\n\t//WEEK8.XA\n\tXA_Darnell,\n\tXA_LitUp,\n\tXA_2Hot,\n\tXA_Blazin,\n\tXA_DarnellIntro,\n} XA_Track;", "XA tracks Weekend")

    replace_once(root / "src/audio.c", "\t{XA_ClwnB, XA_LENGTH(19607)}, //XA_Expurgation\n};", "\t{XA_ClwnB, XA_LENGTH(19607)}, //XA_Expurgation\n\t//WEEK8.XA - song pairs use channels 0/1, 2/3, 4/5, and 6/7\n\t{XA_Week8, XA_LENGTH(12697)}, //XA_Darnell\n\t{XA_Week8, XA_LENGTH(11455)}, //XA_LitUp\n\t{XA_Week8, XA_LENGTH(12000)}, //XA_2Hot\n\t{XA_Week8, XA_LENGTH(12267)}, //XA_Blazin\n\t{XA_DarnIn, XA_LENGTH(1072)}, //XA_DarnellIntro\n};", "XA lengths Weekend")
    replace_once(root / "src/audio.c", "\t\t\"\\\\MUSIC\\\\CLWNB.XA;1\",  //XA_ClwnB\n", "\t\t\"\\\\MUSIC\\\\CLWNB.XA;1\",  //XA_ClwnB\n\t\t\"\\\\MUSIC\\\\WEEK8.XA;1\",  //XA_Week8\n\t\t\"\\\\MUSIC\\\\DARNIN.XA;1\", //XA_DarnIn\n", "XA path Weekend")

    replace_once(root / "src/stage.c", '#include "character/pico.h"\n', '#include "character/pico.h"\n#include "character/picoplayer.h"\n#include "character/nene.h"\n#include "character/darnell.h"\n#include "character/picoblazin.h"\n#include "character/darnellblazin.h"\n', "stage Weekend character includes")
    replace_once(root / "src/stage.c", '#include "stage/week7.h"\n', '#include "stage/week7.h"\n#include "stage/weekend1.h"\n', "stage Weekend include")
    replace_once(root / "src/stage.c", "\t\t\tstage.player->set_anim(stage.player, note_anims[type][0]);\n\t\t\t#ifndef STAGE_FUNKYFRIDAY", "\t\t\tif (!Weekend1_ApplyHit(note))\n\t\t\t\tstage.player->set_anim(stage.player, note_anims[type][0]);\n\t\t\t#ifndef STAGE_FUNKYFRIDAY", "Weekend player note hit")
    replace_once(root / "src/stage.c", "\t\t\t\t\t\tStage_CutVocal();\n\t\t\t\t\t\tStage_MissNote();", "\t\t\t\t\t\tStage_CutVocal();\n\t\t\t\t\t\tWeekend1_ApplyMiss(note);\n\t\t\t\t\t\tStage_MissNote();", "Weekend note miss")
    replace_once(root / "src/stage.c", "\t\t\t\t\tStage_CutVocal();\n\t\t\t\t\tStage_MissNote();\n\t\t\t\t\tstage.health -= 475;", "\t\t\t\t\tStage_CutVocal();\n\t\t\t\t\tWeekend1_ApplyMiss(note);\n\t\t\t\t\tStage_MissNote();\n\t\t\t\t\tstage.health -= 475;", "Weekend legacy note miss")
    replace_once(root / "src/stage.c", "\t\tcase StageId_7_1: // Ugh\n\t\t\treturn true;", "\t\tcase StageId_7_1: // Ugh\n\t\tcase StageId_8_1: // Darnell\n\t\t\treturn true;", "Weekend difficulty")
    replace_once(root / "src/stage.c", "void Stage_Load(StageId id, StageDiff difficulty, boolean story)\n{\n", "void Stage_Load(StageId id, StageDiff difficulty, boolean story)\n{\n\tWeekend1_Reset(id);\n\tWeekend1_PlayIntro(id, story);\n\n", "Weekend intro hook")
    replace_once(root / "src/stage.c", "\t//Load music\n\tStage_LoadMusic();\n}\n\nvoid Stage_Unload", "\t//Load music\n\tStage_LoadMusic();\n\tif (Weekend1_BeginInGameIntro(id, story))\n\t\tstage.state = StageState_WeekendIntro;\n}\n\nvoid Stage_Unload", "Weekend in-game intro start")
    replace_once(root / "src/stage.c", "\tif ((pad_state.press & PAD_START) && Trans_Idle())", "\tif ((pad_state.press & PAD_START) && Trans_Idle() && stage.state != StageState_WeekendIntro)", "Weekend Start skip routing")
    replace_once(root / "src/stage.c", "\tif (stage.cur_section->flag & SECTION_FLAG_OPPFOCUS)\n\t\tStage_FocusCharacter(stage.opponent, FIXED_UNIT / 24);\n\telse\n\t\tStage_FocusCharacter(stage.player, FIXED_UNIT / 24);\n\tstage.camera.x = stage.camera.tx;", "\tif (stage.cur_section->flag & SECTION_FLAG_OPPFOCUS)\n\t\tStage_FocusCharacter(stage.opponent, FIXED_UNIT / 24);\n\telse\n\t\tStage_FocusCharacter(stage.player, FIXED_UNIT / 24);\n\tWeekend1_ApplyCameraTarget();\n\tstage.camera.x = stage.camera.tx;", "Weekend initial camera target")
    replace_once(root / "src/stage.c", "\tstage.camera.zoom = stage.camera.tz;\n\t\n\tstage.bump", "\tstage.camera.zoom = stage.camera.tz;\n\tWeekend1_ApplyCameraZoom();\n\t\n\tstage.bump", "Weekend initial camera zoom")
    replace_once(root / "src/stage.c", "\t\t\t\tif (stage.stage_id <= StageId_LastVanilla)\n", "\t\t\t\tif (!(stage.stage_def->week & 0x80))\n", "Weekend menu return routing")
    replace_once(root / "src/stage.c", "\t\t\t\tLoadScr_End();\n\t\t\t\t\n\t\t\t\tgameloop", "\t\t\t\tWeekend1_ExitStory();\n\t\t\t\tLoadScr_End();\n\t\t\t\t\n\t\t\t\tgameloop", "Weekend story exit")
    replace_once(root / "src/stage.c", "\t\t\t\t\t\tSettings_Save();\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t\tstage.song_time", "\t\t\t\t\t\tSettings_Save();\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t\tif (Weekend1_PlayEnding())\n\t\t\t\t\tgoto StageWorldOnly;\n\t\t\t\tstage.song_time", "Weekend ending movie")
    replace_once(root / "src/stage.c", "\t\t\tif (stage.cur_section->flag & SECTION_FLAG_OPPFOCUS)\n\t\t\t\tStage_FocusCharacter(stage.opponent, FIXED_UNIT / 24);\n\t\t\telse\n\t\t\t\tStage_FocusCharacter(stage.player, FIXED_UNIT / 24);\n\t\t\tStage_ScrollCamera();", "\t\t\tif (stage.cur_section->flag & SECTION_FLAG_OPPFOCUS)\n\t\t\t\tStage_FocusCharacter(stage.opponent, FIXED_UNIT / 24);\n\t\t\telse\n\t\t\t\tStage_FocusCharacter(stage.player, FIXED_UNIT / 24);\n\t\t\tWeekend1_ApplyCameraTarget();\n\t\t\tStage_ScrollCamera();\n\t\t\tWeekend1_ApplyCameraZoom();", "Weekend live camera")
    replace_once(root / "src/stage.c", "\t\t\t\t\tstage.opponent->set_anim(stage.opponent, note_anims[note->type & 0x3][(note->type & NOTE_FLAG_ALT_ANIM) != 0]);", "\t\t\t\t\tif (!Weekend1_ApplyHit(note))\n\t\t\t\t\t\tstage.opponent->set_anim(stage.opponent, note_anims[note->type & 0x3][(note->type & NOTE_FLAG_ALT_ANIM) != 0]);", "Weekend opponent note hit")
    replace_once(root / "src/stage.c", "\t\t\t//Hardcoded stage stuff", "\t\t\tStageWorldOnly:;\n\t\t\t//Hardcoded stage stuff", "Weekend world-only draw label")
    replace_once(root / "src/stage.c", "\t\tcase StageState_Pause:\n", "\t\tcase StageState_WeekendIntro:\n\t\t{\n\t\t\tstage.flag &= ~STAGE_FLAG_JUST_STEP;\n\t\t\tif (!Weekend1_InGameIntroTick())\n\t\t\t{\n\t\t\t\tStage_LoadMusic();\n\t\t\t\tstage.state = StageState_Play;\n\t\t\t\tTimer_Reset();\n\t\t\t}\n\t\t\tgoto StageWorldOnly;\n\t\t}\n\t\tcase StageState_Pause:\n", "Weekend in-game intro tick")

    # Blazin' uses the official hidden opponent lane and centered player lane.
    replace_once(root / "src/stage.c", "static const u16 note_key[]", "static fixed_t Stage_NoteX(u8 lane)\n{\n\tif (Weekend1_MiddleScroll() && lane < 4)\n\t\treturn FIXED_DEC(-51 + lane * 34,1);\n\treturn note_x[lane];\n}\n\nstatic const u16 note_key[]", "Blazin middle note helper")
    stage_c = root / "src/stage.c"
    text = stage_c.read_text().replace("note_x[note->type & 0x7]", "Stage_NoteX(note->type & 0x7)")
    text = text.replace("note_x[i]", "Stage_NoteX(i)")
    text = text.replace("note_x[i | 0x4]", "Stage_NoteX(i | 0x4)")
    stage_c.write_text(text)
    replace_once(root / "src/stage.c", "\t\t\t\t//Opponent\n\t\t\t\tnote_dst.x = Stage_NoteX(i | 0x4) - FIXED_DEC(16,1);\n\t\t\t\t\n\t\t\t\tnote_src.x = 0;\n\t\t\t\tnote_src.y = i << 5;\n\t\t\t\tStage_DrawTex(&stage.tex_hud0, &note_src, &note_dst, stage.bump);", "\t\t\t\t//Opponent lane is deliberately hidden in Blazin'.\n\t\t\t\tif (!Weekend1_MiddleScroll())\n\t\t\t\t{\n\t\t\t\t\tnote_dst.x = Stage_NoteX(i | 0x4) - FIXED_DEC(16,1);\n\t\t\t\t\tnote_src.x = 0;\n\t\t\t\t\tnote_src.y = i << 5;\n\t\t\t\t\tStage_DrawTex(&stage.tex_hud0, &note_src, &note_dst, stage.bump);\n\t\t\t\t}", "Blazin hide opponent strums")
    replace_once(root / "src/stage.c", "\t\telse\n\t\t{\n\t\t\t//Don't draw if below screen\n\t\t\tRECT note_src;", "\t\telse\n\t\t{\n\t\t\t//Blazin' keeps opponent timing active but does not render its lane.\n\t\t\tif (Weekend1_MiddleScroll() && (note->type & NOTE_FLAG_OPPONENT))\n\t\t\t\tcontinue;\n\t\t\t//Don't draw if below screen\n\t\t\tRECT note_src;", "Blazin hide opponent notes")

    # Movie playback: missing media is fatal, while Start skip is valid.
    (root / "src/movie.c").write_text(r'''#include "movie.h"

#include "psx.h"
#include "main.h"

#include "strplay.c"

void Movie_Play(const char *path, unsigned long length)
{
	CdlFILE file;
	if (CdSearchFile(&file, path) == 0)
	{
		sprintf(error_msg, "[Movie_Play] Missing \"%s\"", path);
		ErrorLock();
		return;
	}
	while (PadRead(1) & PADstart)
		VSync(0);
	STRFILE sfile;
	strcpy(sfile.FileName, path);
	sfile.Xres = 320;
	sfile.Yres = 240;
	sfile.NumFrames = length;
	PlayStr(320, 240, 0, 0, &sfile);
}
''')

    # Add definitions after every pre-existing mod stage, preserving their IDs/content.
    stagedefs = root / "src/stagedef_disc1.h"
    text = stagedefs.read_text()
    text = text.rstrip()
    if not text.endswith("\t}"):
        raise SystemExit("stagedef append: final definition not found")
    stagedefs.write_text(text + "," + WEEK8_DEFS)

    xml = root / "funkin.xml"
    replace_once(xml, "\t\t\t<!-- Kapi assets -->", WEEK8_XML + "\t\t\t<!-- Kapi assets -->", "Weekend XML charts")
    replace_once(xml, "\t\t\t\t<file name = \"pico.arc\" type = \"data\" source = \"iso/pico/main.arc\"/>\n", "\t\t\t\t<file name = \"pico.arc\" type = \"data\" source = \"iso/pico/main.arc\"/>\n\t\t\t\t<file name = \"picoplay.arc\" type = \"data\" source = \"iso/picoplay.arc\"/>\n\t\t\t\t<file name = \"nene.arc\" type = \"data\" source = \"iso/nene.arc\"/>\n\t\t\t\t<file name = \"darnell.arc\" type = \"data\" source = \"iso/darnell.arc\"/>\n\t\t\t\t<file name = \"picobl.arc\" type = \"data\" source = \"iso/picobl.arc\"/>\n\t\t\t\t<file name = \"darnbl.arc\" type = \"data\" source = \"iso/darnbl.arc\"/>\n", "Weekend XML characters")
    replace_once(xml, "\t\t\t\t<file name = \"week7b.xa\" type = \"xa\" source = \"iso/music/week7b.xa\"/>\n\t\t\t\t<dummy sectors=\"128\"/>\n", "\t\t\t\t<file name = \"week7b.xa\" type = \"xa\" source = \"iso/music/week7b.xa\"/>\n\t\t\t\t<dummy sectors=\"128\"/>\n\t\t\t\t<file name = \"week8.xa\" type = \"xa\" source = \"iso/music/week8.xa\"/>\n\t\t\t\t<file name = \"darnin.xa\" type = \"xa\" source = \"iso/music/darnin.xa\"/>\n\t\t\t\t<dummy sectors=\"128\"/>\n", "Weekend XML audio")
    replace_once(xml, "\t\t\t<!-- Dummy sectors -->", "\t\t\t<!-- Weekend 1 FMV cutscenes -->\n\t\t\t<dir name = \"movie\">\n\t\t\t\t<file name = \"darnell.str\" type = \"xa\" source = \"iso/movie/darnell.str\"/>\n\t\t\t\t<file name = \"2hot.str\" type = \"xa\" source = \"iso/movie/2hot.str\"/>\n\t\t\t\t<file name = \"blazin.str\" type = \"xa\" source = \"iso/movie/blazin.str\"/>\n\t\t\t</dir>\n\n\t\t\t<!-- Dummy sectors -->", "Weekend XML movies")

    # Story Mode and Freeplay additions use the existing official v0.8.4 UI.
    menu = root / "src/menu.c"
    replace_once(menu, "\t\t\t\tconst char *tracks[3];", "\t\t\t\tconst char *tracks[4];", "Weekend story track count")
    replace_once(menu, "\t\t\t\t{\"7\", StageId_7_1, \"TANKMAN\", {\"UGH\", \"GUNS\", \"STRESS\"}},", "\t\t\t\t{\"7\", StageId_7_1, \"TANKMAN\", {\"UGH\", \"GUNS\", \"STRESS\"}},\n\t\t\t\t{\"8\", StageId_8_1, \"DUE DEBTS\", {\"DARNELL\", \"LIT UP\", \"TWO HOT\", \"BLAZIN'\"}},", "Weekend story entry")
    replace_once(menu, "\t\t\tfor (int i = 0; i < COUNT_OF(menu_options[menu.select].tracks); i++)\n\t\t\t{\n\t\t\t\tmenu.font_bold.draw", "\t\t\tfor (int i = 0; i < COUNT_OF(menu_options[menu.select].tracks); i++)\n\t\t\t{\n\t\t\t\tif (menu_options[menu.select].tracks[i] == NULL)\n\t\t\t\t\tcontinue;\n\t\t\t\tmenu.font_bold.draw", "Weekend Story nullable fourth track")
    replace_once(menu, "#define MENU_FP_SONG_COUNT 22", "#define MENU_FP_SONG_COUNT 26", "Weekend Freeplay count")
    replace_once(menu, "\t{StageId_7_3, XA_Stress, 0, \"STRESS\", \"WEEK 7\", 178, 178, {3,4,5,0,0}, 1, 16},\n};", "\t{StageId_7_3, XA_Stress, 0, \"STRESS\", \"WEEK 7\", 178, 178, {3,4,5,0,0}, 1, 16},\n\t{StageId_8_1, XA_Darnell, 0, \"DARNELL\", \"WEEKEND 1\", 150, 180, {2,3,4,8,9}, 2, 18},\n\t{StageId_8_2, XA_LitUp, 2, \"LIT UP\", \"WEEKEND 1\", 176, 176, {2,3,4,0,0}, 2, 18},\n\t{StageId_8_3, XA_2Hot, 4, \"TWO HOT\", \"WEEKEND 1\", 182, 182, {3,4,5,0,0}, 2, 18},\n\t{StageId_8_4, XA_Blazin, 6, \"BLAZIN'\", \"WEEKEND 1\", 180, 180, {3,4,5,0,0}, 2, 18},\n};", "Weekend Freeplay entries")
    replace_once(menu, "\telse\n\t{\n\t\t//Week\n\t\tRECT label_src", "\telse\n\t{\n\t\tif (week[0] == '8' && week[1] == '\\0')\n\t\t{\n\t\t\tmenu.font_bold.draw(&menu.font_bold, \"WEEKEND ONE\", x, y + 8, FontAlign_Left);\n\t\t\treturn;\n\t\t}\n\t\t//Week\n\t\tRECT label_src", "Weekend Story label")

    # Pause metadata follows StageId ordering, including mods before Weekend 1.
    replace_once(root / "src/stage.c", "\t\t\"IMPROBABLE OUTSET\", \"MADNESS\", \"HELLCLOWN\", \"EXPURGATION\",\n", "\t\t\"IMPROBABLE OUTSET\", \"MADNESS\", \"HELLCLOWN\", \"EXPURGATION\",\n\t\t\"DARNELL\", \"LIT UP\", \"TWO HOT\", \"BLAZIN'\",\n", "Weekend pause song names")

    print("Weekend 1 v2 runtime applied additively")


if __name__ == "__main__":
    main()
