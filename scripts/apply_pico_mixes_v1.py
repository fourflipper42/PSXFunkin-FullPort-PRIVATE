#!/usr/bin/env python3
"""Apply all fifteen official v0.8.4 Pico Mixes and Pico menu routing."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


SONGS = (
    ("Bopeebo", "BOPEEBO", "1_1", "Bopeebo", 100),
    ("Fresh", "FRESH", "1_2", "Fresh", 120),
    ("Dadbattle", "DADBATTLE", "1_3", "Dadbattle", 180),
    ("Spookeez", "SPOOKEEZ", "2_1", "Spookeez", 150),
    ("South", "SOUTH", "2_2", "South", 165),
    ("Pico", "PICO", "3_1", "Pico", 150),
    ("Philly", "PHILLY NICE", "3_2", "Philly", 175),
    ("Blammed", "BLAMMED", "3_3", "Blammed", 165),
    ("Cocoa", "COCOA", "5_1", "Cocoa", 100),
    ("Eggnog", "EGGNOG", "5_2", "Eggnog", 150),
    ("Senpai", "SENPAI", "6_1", "Senpai", 144),
    ("Roses", "ROSES", "6_2", "Roses", 120),
    ("Ugh", "UGH", "7_1", "Ugh", 160),
    ("Guns", "GUNS", "7_2", "Guns", 185),
    ("Stress", "STRESS", "7_3", "Stress", 178),
)

# Exact official v0.8.4 Pico Mix chart speeds (easy, normal, hard), stored in
# tenths so generated PS1 stage definitions remain compile-time constants.
SCROLLS = (
    (15, 18, 23), (16, 20, 23), (22, 24, 26), (23, 24, 26), (16, 24, 24),
    (18, 22, 25), (23, 26, 26), (24, 25, 26), (23, 26, 27), (23, 25, 27),
    (21, 22, 24), (21, 23, 26), (22, 26, 26), (21, 23, 26), (25, 29, 32),
)


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def replace_file(path: Path, old: str, new: str, label: str) -> None:
    path.write_text(once(path.read_text(), old, new, label))


def extract_definition(text: str, stage_id: str) -> str:
    marker = f"\t{{ //StageId_{stage_id} "
    start = text.find(marker)
    if start < 0:
        raise SystemExit(f"source definition StageId_{stage_id} missing")
    depth = 0
    found = False
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
            found = True
        elif char == "}":
            depth -= 1
            if found and depth == 0:
                return text[start:index + 1]
    raise SystemExit(f"unterminated definition StageId_{stage_id}")


def pico_definition(source: str, index: int, key: str, original: str) -> str:
    block = extract_definition(source, original)
    block = re.sub(
        rf"^\t\{{ //StageId_{re.escape(original)}[^\n]*",
        f"\t{{ //StageId_PM_{key} ({SONGS[index][1]} Pico Mix)",
        block,
        count=1,
        flags=re.M,
    )
    replacements = {
        "Char_BF_New": "Char_PicoPlayer_New",
        "Char_XmasBF_New": "Char_PicoXmas_New",
        "Char_BFWeeb_New": "Char_PicoPixel_New",
    }
    if index in (3, 4):
        replacements.update({
            "Char_BF_New": "Char_PicoDark_New",
            "Char_Spook_New": "Char_SpookyDark_New",
            "Char_GF_New": "Char_NeneDark_New",
        })
    elif index in (8, 9):
        replacements.update({
            "Char_XmasGF_New": "Char_NeneXmas_New",
        })
    elif index in (10, 11):
        replacements.update({
            "Char_GFWeeb_New": "Char_NenePixel_New",
        })
    elif index == 14:
        replacements.update({
            "Char_BF_New": "Char_PicoHold_New",
            "Char_Tank_New": "Char_TankBloody_New",
            "Char_GF_New": "Char_Otis_New",
        })
    else:
        replacements.update({"Char_GF_New": "Char_Nene_New"})
    for old, new in replacements.items():
        block = block.replace(old, new)

    easy, normal, hard = SCROLLS[index]
    speed = (
        f"{{FIXED_DEC({easy},10),FIXED_DEC({normal},10),"
        f"FIXED_DEC({hard},10)}}"
    )
    block, speed_count = re.subn(
        r"\{FIXED_DEC\([0-9]+,[0-9]+\),\s*FIXED_DEC\([0-9]+,[0-9]+\),"
        r"\s*FIXED_DEC\([0-9]+,[0-9]+\)\}",
        speed,
        block,
        count=1,
    )
    if speed_count != 1:
        raise SystemExit(f"could not rewrite official Pico scroll speeds for {key}")

    # All Pico mixes live in chart week 10 and are standalone Freeplay songs.
    block = re.sub(
        r"\n\t\t[0-9]+, [0-9]+,\n\t\tXA_[A-Za-z0-9_]+, [0-9]+,\n\t\t\n\t\tStageId_[A-Za-z0-9_]+, [^\n]+",
        f"\n\t\t10, {index + 1},\n\t\tXA_PM_{key}, {(index % 4) * 2},\n\t\t\n\t\tStageId_PM_{key}, 0",
        block,
        count=1,
    )
    if f"XA_PM_{key}" not in block:
        raise SystemExit(f"could not rewrite Pico definition {key}")
    return block


PICO_H = r'''#ifndef _PICO_MIX_H
#define _PICO_MIX_H

#include "../stage.h"

boolean PicoMix_IsStage(StageId id);
void PicoMix_Reset(StageId id);
void PicoMix_Start(void);
void PicoMix_PlayIntro(StageId id);
void PicoMix_PlayEnding(void);
void PicoMix_Exit(void);
boolean PicoMix_ApplyHit(const Note *note);
void PicoMix_ApplyMiss(const Note *note);
boolean PicoMix_PlayMissDirection(u8 direction);
void PicoMix_ApplyCameraTarget(void);
void PicoMix_ApplyCameraZoom(void);
boolean PicoMix_DrawHealthIcon(s8 side);

#endif
'''


PICO_C = r'''#include "picomix.h"

#include "../main.h"
#include "../movie.h"
#include "../timer.h"

#include "../character/picoplayer.h"
#include "../character/picodark.h"
#include "../character/picoxmas.h"
#include "../character/picopixel.h"
#include "../character/picohold.h"
#include "../character/spookydark.h"
#include "../character/tankbloody.h"

typedef struct
{
    u16 step;
    u8 kind, flags;
    s16 a, b, c;
} PicoMixEvent;

#include "../pico_mix_events_generated.h"
#include "../pico_mix_movies_generated.h"

enum
{
    PMEvent_Focus = 1,
    PMEvent_Zoom,
    PMEvent_Bop,
    PMEvent_Scroll,
    PMEvent_Animation,
    PMEvent_Mask,
    PMEvent_HealthIcon,
};

static boolean pm_active = false;
static boolean pm_ready = false;
static boolean pm_bloody_icon = false;
static boolean pm_ending_played = false;
static boolean pm_stress_session_active = false;
static u8 pm_song = 0;
static u16 pm_event = 0, pm_event_end = 0;
static u8 pm_focus = 0;
static s16 pm_focus_x = 0, pm_focus_y = 0;
static fixed_t pm_focus_from_x = 0, pm_focus_from_y = 0;
static fixed_t pm_focus_to_x = 0, pm_focus_to_y = 0;
static s16 pm_focus_start = 0, pm_focus_end = -1;
static u8 pm_focus_ease = 0;
static fixed_t pm_zoom = FIXED_UNIT, pm_zoom_from = FIXED_UNIT, pm_zoom_to = FIXED_UNIT;
static s16 pm_zoom_start = 0, pm_zoom_end = -1;
static u8 pm_zoom_ease = 7;
static fixed_t pm_base_speed = FIXED_UNIT;
static fixed_t pm_scroll_from = FIXED_UNIT, pm_scroll_to = FIXED_UNIT;
static s16 pm_scroll_start = 0, pm_scroll_end = -1;
static u8 pm_scroll_ease = 7;
static s16 pm_bop_rate = 16, pm_bop_offset = 0;
static fixed_t pm_bop_zoom = FIXED_DEC(1015,1000);
static Gfx_Tex pm_bloody_health_tex;

static fixed_t PM_Ease(fixed_t t, u8 ease)
{
    fixed_t inv, square, fourth;
    if (t <= 0) return 0;
    if (t >= FIXED_UNIT) return FIXED_UNIT;
    switch (ease)
    {
        case 1: /* expoOut -- close fixed-point fifth-power curve */
            inv = FIXED_UNIT - t;
            square = FIXED_MUL(inv, inv);
            fourth = FIXED_MUL(square, square);
            return FIXED_UNIT - FIXED_MUL(fourth, inv);
        case 2: /* quadInOut */
            if (t < FIXED_UNIT / 2)
                return FIXED_MUL(FIXED_DEC(2,1), FIXED_MUL(t,t));
            t = FIXED_UNIT - t;
            return FIXED_UNIT - FIXED_MUL(FIXED_DEC(2,1), FIXED_MUL(t,t));
        case 3: /* quartOut */
            inv = FIXED_UNIT - t;
            square = FIXED_MUL(inv, inv);
            return FIXED_UNIT - FIXED_MUL(square, square);
        case 4: /* circOut approximation without an expensive square root */
            inv = FIXED_UNIT - t;
            return FIXED_UNIT - FIXED_MUL(inv, inv);
        case 5: /* cubeInOut */
            if (t < FIXED_UNIT / 2)
                return FIXED_MUL(FIXED_DEC(4,1), FIXED_MUL(FIXED_MUL(t,t),t));
            t = FIXED_UNIT - t;
            return FIXED_UNIT - FIXED_MUL(FIXED_DEC(4,1), FIXED_MUL(FIXED_MUL(t,t),t));
        case 6: /* quartInOut */
            if (t < FIXED_UNIT / 2)
            {
                square = FIXED_MUL(t, t);
                return FIXED_MUL(FIXED_DEC(8,1), FIXED_MUL(square, square));
            }
            inv = FIXED_UNIT - t;
            square = FIXED_MUL(inv, inv);
            return FIXED_UNIT - FIXED_MUL(FIXED_DEC(8,1), FIXED_MUL(square, square));
        default:
            return t;
    }
}

static Character *PM_FocusCharacter(void)
{
    if (pm_focus == 1) return stage.opponent;
    if (pm_focus == 2) return stage.gf;
    return stage.player;
}

static void PM_FocusPosition(fixed_t *x, fixed_t *y)
{
    Character *focus = PM_FocusCharacter();
    *x = focus->x + focus->focus_x + FIXED_DEC(pm_focus_x,1);
    *y = focus->y + focus->focus_y + FIXED_DEC(pm_focus_y,1);
}

static fixed_t PM_StepPosition(void)
{
    return stage.note_scroll / 12;
}

static fixed_t PM_TweenAmount(fixed_t step, s16 start, s16 end, u8 ease)
{
    if (end <= start || step >= ((fixed_t)end << FIXED_SHIFT))
        return FIXED_UNIT;
    if (step <= ((fixed_t)start << FIXED_SHIFT))
        return 0;
    return PM_Ease(
        FIXED_DIV(step - ((fixed_t)start << FIXED_SHIFT),
                  ((fixed_t)(end - start) << FIXED_SHIFT)),
        ease
    );
}

static void PM_UpdateTweens(fixed_t step)
{
    if (pm_focus_end >= pm_focus_start)
    {
        fixed_t t = PM_TweenAmount(step, pm_focus_start, pm_focus_end, pm_focus_ease);
        stage.camera.tx = pm_focus_from_x + FIXED_MUL(pm_focus_to_x - pm_focus_from_x, t);
        stage.camera.ty = pm_focus_from_y + FIXED_MUL(pm_focus_to_y - pm_focus_from_y, t);
        if (t >= FIXED_UNIT) pm_focus_end = -1;
    }
    if (pm_zoom_end >= pm_zoom_start)
    {
        fixed_t t = PM_TweenAmount(step, pm_zoom_start, pm_zoom_end, pm_zoom_ease);
        pm_zoom = pm_zoom_from + FIXED_MUL(pm_zoom_to - pm_zoom_from, t);
        if (t >= FIXED_UNIT) pm_zoom_end = -1;
    }
    if (pm_scroll_end >= pm_scroll_start)
    {
        fixed_t t = PM_TweenAmount(step, pm_scroll_start, pm_scroll_end, pm_scroll_ease);
        stage.speed = pm_scroll_from + FIXED_MUL(pm_scroll_to - pm_scroll_from, t);
        if (t >= FIXED_UNIT) pm_scroll_end = -1;
    }
}

boolean PicoMix_IsStage(StageId id)
{
    return id >= StageId_PM_Bopeebo && id <= StageId_PM_Stress;
}

void PicoMix_Reset(StageId id)
{
    pm_active = PicoMix_IsStage(id);
    pm_ready = false;
    pm_bloody_icon = false;
    pm_ending_played = false;
    if (!pm_active) return;
    pm_song = (u8)(id - StageId_PM_Bopeebo);
    pm_event = pico_mix_event_start[pm_song];
    pm_event_end = pm_event + pico_mix_event_count[pm_song];
    pm_focus = 0;
    pm_focus_x = pm_focus_y = 0;
    pm_focus_end = pm_zoom_end = pm_scroll_end = -1;
    {
        static const fixed_t default_zoom[] = {
            FIXED_DEC(85,100), FIXED_DEC(85,100), FIXED_DEC(85,100),
            FIXED_DEC(1,1), FIXED_DEC(1,1),
            FIXED_DEC(11,10), FIXED_DEC(11,10), FIXED_DEC(11,10),
            FIXED_DEC(8,10), FIXED_DEC(8,10),
            FIXED_DEC(1,1), FIXED_DEC(1,1),
            FIXED_DEC(7,10), FIXED_DEC(7,10), FIXED_DEC(7,10),
        };
        pm_zoom = pm_zoom_from = pm_zoom_to = default_zoom[pm_song];
    }
    pm_bop_rate = 16;
    pm_bop_offset = 0;
    pm_bop_zoom = FIXED_DEC(1015,1000);
    if (pm_song == 14)
        Gfx_LoadTex(&pm_bloody_health_tex, IO_Read("\\STAGE\\PMBLOOD.TIM;1"), GFX_LOADTEX_FREE);
}

void PicoMix_Start(void)
{
    if (!pm_active) return;
    pm_ready = true;
    pm_base_speed = stage.speed;
    pm_scroll_from = pm_scroll_to = stage.speed;
}

void PicoMix_PlayIntro(StageId id)
{
    if (id == StageId_PM_Stress && !pm_stress_session_active)
    {
        pm_stress_session_active = true;
        Movie_Play("\\MOVIE\\PSTRS.STR;1", PICO_STRESS_INTRO_FRAMES);
    }
}

void PicoMix_PlayEnding(void)
{
    if (pm_active && pm_song == 14 && !pm_ending_played)
    {
        pm_ending_played = true;
        Movie_Play("\\MOVIE\\PSTREND.STR;1", PICO_STRESS_END_FRAMES);
    }
}

void PicoMix_Exit(void)
{
    pm_stress_session_active = false;
}

static void PM_PlayerAnimation(u8 animation)
{
    u8 value = 0;
    if (pm_song <= 2 || (pm_song >= 5 && pm_song <= 7) || (pm_song >= 12 && pm_song <= 13))
    {
        static const u8 regular[] = {
            0, PicoPlayer_Hey, PicoPlayer_Cheer, PicoPlayer_BurpShit,
            PicoPlayer_BurpSmile, PicoPlayer_BurpShit, 0,
        };
        if (animation < sizeof(regular)) value = regular[animation];
    }
    else if (pm_song == 3 || pm_song == 4)
    {
        static const u8 dark[] = {
            0, PicoDark_Hey, PicoDark_Cheer, PicoDark_BurpShit,
            PicoDark_BurpSmile, PicoDark_BurpShit, 0,
        };
        if (animation < sizeof(dark)) value = dark[animation];
    }
    else if (pm_song == 14 && animation == 6)
        value = PicoHold_KnifeToss;
    if (value != 0)
        stage.player->set_anim(stage.player, value);
}

static void PM_OpponentAnimation(u8 animation)
{
    if ((pm_song == 3 || pm_song == 4) && animation == 2)
        stage.opponent->set_anim(stage.opponent, SpookyDark_Cheer);
    else if ((pm_song == 12 || pm_song == 13) && animation == 1)
        stage.opponent->set_anim(stage.opponent, CharAnim_UpAlt);
    else if ((pm_song == 12 || pm_song == 13) && animation == 3)
        stage.opponent->set_anim(stage.opponent, CharAnim_DownAlt);
    else if (pm_song == 14 && animation == 3)
        stage.opponent->set_anim(stage.opponent, TankBloody_PrettyGood);
    else if (pm_song == 14 && animation == 4)
        stage.opponent->set_anim(stage.opponent, TankBloody_Redheads);
}

static void PM_ApplyEvent(const PicoMixEvent *event)
{
    switch (event->kind)
    {
        case PMEvent_Focus:
            pm_focus = event->flags & 3;
            pm_focus_x = event->a;
            pm_focus_y = event->b;
            pm_focus_ease = event->flags >> 2;
            if (pm_focus_ease == 0 || event->c == 0)
            {
                pm_focus_end = -1;
            }
            else
            {
                pm_focus_from_x = stage.camera.x;
                pm_focus_from_y = stage.camera.y;
                PM_FocusPosition(&pm_focus_to_x, &pm_focus_to_y);
                pm_focus_start = event->step;
                pm_focus_end = event->step + event->c;
            }
            break;
        case PMEvent_Zoom:
            pm_zoom_from = pm_zoom;
            pm_zoom_to = event->a;
            pm_zoom_start = event->step;
            pm_zoom_end = event->b > 0 ? event->step + event->b : event->step;
            pm_zoom_ease = event->c;
            if (event->b == 0) pm_zoom = pm_zoom_to;
            break;
        case PMEvent_Bop:
            pm_bop_rate = event->a;
            pm_bop_zoom = event->b;
            pm_bop_offset = event->c;
            break;
        case PMEvent_Scroll:
            pm_scroll_from = stage.speed;
            pm_scroll_to = (event->flags & 1) ? event->a : FIXED_MUL(pm_base_speed, event->a);
            pm_scroll_start = event->step;
            pm_scroll_end = event->b > 0 ? event->step + event->b : event->step;
            pm_scroll_ease = event->c;
            if (event->b == 0) stage.speed = pm_scroll_to;
            break;
        case PMEvent_Animation:
            if (event->flags & 1) PM_OpponentAnimation(event->a);
            else PM_PlayerAnimation(event->a);
            break;
        case PMEvent_Mask:
            /* The PS1 renderer has no per-character shader framebuffer. The
             * converted bloody Tankman art already carries its authored blood
             * pixels, so never substitute an incorrect full-screen effect. */
            break;
        case PMEvent_HealthIcon:
            pm_bloody_icon = true;
            break;
        default:
            break;
    }
}

static void PM_TickEvents(void)
{
    if (!pm_active || !pm_ready) return;
    s16 step = stage.song_step;
    fixed_t step_position = PM_StepPosition();
    PM_UpdateTweens(step_position);
    while (pm_event < pm_event_end && pico_mix_events[pm_event].step <= step)
        PM_ApplyEvent(&pico_mix_events[pm_event++]);
    PM_UpdateTweens(step_position);

    if (stage.flag & STAGE_FLAG_JUST_STEP)
    {
        boolean bop = stage.song_step >= 0 && pm_bop_rate > 0 &&
            ((stage.song_step + pm_bop_offset) % pm_bop_rate) == 0;
        if (bop)
        {
            stage.bump = pm_bop_zoom;
            stage.sbump = FIXED_UNIT + ((pm_bop_zoom - FIXED_UNIT) << 1);
        }
        else
        {
            if ((stage.song_step & 0xF) == 0) stage.bump = FIXED_UNIT;
            if ((stage.song_step & 0x3) == 0) stage.sbump = FIXED_UNIT;
        }
    }
}

boolean PicoMix_ApplyHit(const Note *note)
{
    if (!pm_active) return false;
    if (note->pad == 50) return true;
    if (!(note->type & NOTE_FLAG_OPPONENT) && note->pad == 51)
    {
        if (pm_song == 5)
            stage.player->set_anim(stage.player, PicoPlayer_BurpCensor);
        return true;
    }
    return false;
}

static u8 PM_MissAnimation(u8 direction)
{
    direction &= 3;
    if (pm_song == 3 || pm_song == 4) return PicoDark_Miss_Left + direction;
    if (pm_song == 8 || pm_song == 9) return PicoXmas_Miss_Left + direction;
    if (pm_song == 10 || pm_song == 11) return PicoPixel_Miss_Left + direction;
    if (pm_song == 14) return PicoHold_Miss_Left + direction;
    return PicoPlayer_Miss_Left + direction;
}

boolean PicoMix_PlayMissDirection(u8 direction)
{
    if (!pm_active) return false;
    stage.player->set_anim(stage.player, PM_MissAnimation(direction));
    return true;
}

void PicoMix_ApplyMiss(const Note *note)
{
    if (pm_active)
        stage.player->set_anim(stage.player, PM_MissAnimation(note->type));
}

void PicoMix_ApplyCameraTarget(void)
{
    PM_TickEvents();
    if (!pm_active || !pm_ready) return;
    if (pm_focus_end < pm_focus_start)
    {
        PM_FocusPosition(&stage.camera.tx, &stage.camera.ty);
        stage.camera.td = FIXED_UNIT / 24;
    }
    else
    {
        stage.camera.td = FIXED_UNIT;
    }
}

void PicoMix_ApplyCameraZoom(void)
{
    if (pm_active && pm_ready)
    {
        stage.camera.zoom = pm_zoom;
        stage.camera.tz = pm_zoom;
        stage.camera.bzoom = FIXED_MUL(stage.camera.zoom, stage.bump);
    }
}

boolean PicoMix_DrawHealthIcon(s8 side)
{
    if (!pm_active || pm_song != 14 || side >= 0 || !pm_bloody_icon)
        return false;
    s8 dying = (stage.health >= 18000) * 24;
    fixed_t hx = (128 << FIXED_SHIFT) * (10000 - stage.health) / 10000;
    RECT src = {dying, 0, 24, 24};
    RECT_FIXED dst = {
        hx + side * FIXED_DEC(11,1) - FIXED_DEC(12,1),
        (SCREEN_HEIGHT2 - 32 + 4 - 12) << FIXED_SHIFT,
        FIXED_DEC(24,1), FIXED_DEC(24,1)
    };
    if (stage.downscroll) dst.y = -dst.y - dst.h;
    Stage_DrawTex(&pm_bloody_health_tex, &src, &dst, FIXED_MUL(stage.bump, stage.sbump));
    return true;
}
'''


def freeplay_entries() -> str:
    album = (3, 3, 3, 3, 3, 5, 3, 3, 5, 3, 5, 5, 3, 3, 5)
    icon = (8, 8, 8, 9, 9, 11, 11, 11, 13, 13, 14, 14, 16, 16, 16)
    ratings = (
        "{1,2,3,0,0}", "{2,3,4,0,0}", "{3,4,5,0,0}",
        "{1,2,3,0,0}", "{2,3,4,0,0}", "{2,3,4,0,0}",
        "{2,3,4,0,0}", "{3,4,5,0,0}", "{2,3,4,0,0}",
        "{3,4,5,0,0}", "{1,2,3,0,0}", "{2,3,4,0,0}",
        "{2,3,4,0,0}", "{3,4,5,0,0}", "{4,5,6,0,0}",
    )
    rows = []
    for index, (key, display, _original, _track, bpm) in enumerate(SONGS):
        rows.append(
            f'\t{{StageId_PM_{key}, XA_PM_{key}, {(index % 4) * 2}, '
            f'"{display}", "PICO MIX", {bpm}, {bpm}, {ratings[index]}, '
            f'{album[index]}, {icon[index]}}},'
        )
    return "\n".join(rows)


def apply_freeplay(menu: Path) -> None:
    text = menu.read_text()
    text = once(text, "#define MENU_FP_SONG_COUNT 27", "#define MENU_FP_SONG_COUNT 42", "Pico Freeplay total")
    text = once(
        text,
        "#define MENU_FP_OPTION_COUNT (MENU_FP_SONG_COUNT + 1)",
        "#define MENU_FP_RANDOM_OPTION 0\n"
        "static const u8 menu_fp_bf_songs[] = {\n"
        "\t0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,26\n"
        "};\n"
        "static const u8 menu_fp_pico_songs[] = {\n"
        "\t22,23,24,25,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41\n"
        "};\n"
        "static u8 Menu_FreeplaySongCount(void)\n"
        "{\n"
        "\treturn menu_freeplay_player == MenuPlayer_Pico ? COUNT_OF(menu_fp_pico_songs) : COUNT_OF(menu_fp_bf_songs);\n"
        "}\n"
        "static u8 Menu_FreeplayOptionCount(void) { return Menu_FreeplaySongCount() + 1; }",
        "Pico Freeplay filters",
    )
    # The random macro was moved into the replacement above.
    text = once(text, "#define MENU_FP_RANDOM_OPTION 0\n#define MENU_FP_META_CELL", "#define MENU_FP_META_CELL", "deduplicate random macro")
    text = once(
        text,
        '\t{StageId_SF_1, XA_Spaghetti, 0, "SPAGHETTI", "SP. COLLAB 1", 112, 112, {2,3,5,0,0}, 3, 19},\n};',
        '\t{StageId_SF_1, XA_Spaghetti, 0, "SPAGHETTI", "SP. COLLAB 1", 112, 112, {2,3,5,0,0}, 3, 19},\n'
        + freeplay_entries() + "\n};",
        "Pico Freeplay entries",
    )
    text = once(
        text,
        "static u8 Menu_FreeplaySongIndex(u8 option)\n"
        "{\n"
        "\tif (option == MENU_FP_RANDOM_OPTION)\n"
        "\t\treturn menu_fp_random_pick % MENU_FP_SONG_COUNT;\n"
        "\treturn (option - 1) % MENU_FP_SONG_COUNT;\n"
        "}",
        "static u8 Menu_FreeplaySongIndex(u8 option)\n"
        "{\n"
        "\tconst u8 *songs = menu_freeplay_player == MenuPlayer_Pico ? menu_fp_pico_songs : menu_fp_bf_songs;\n"
        "\tu8 count = Menu_FreeplaySongCount();\n"
        "\tu8 local = option == MENU_FP_RANDOM_OPTION ? menu_fp_random_pick % count : (option - 1) % count;\n"
        "\treturn songs[local];\n"
        "}",
        "Pico Freeplay song mapping",
    )
    if "static u32 menu_fp_favorites[2] = {0, 0};" not in text:
        raise SystemExit("Pico Freeplay requires the console save's 64-slot favorites bank")
    text = once(
        text,
        ": menu_fp_songs[option - 1].text;",
        ": menu_fp_songs[Menu_FreeplaySongIndex(option)].text;",
        "Pico filtered visible labels",
    )
    text = once(
        text,
        "\t\t\t\t\tif (menu_freeplay_player == MenuPlayer_Boyfriend)\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\tmenu_freeplay_song = menu.select;",
        "\t\t\t\t\tif (menu_freeplay_player == MenuPlayer_Boyfriend || menu_freeplay_player == MenuPlayer_Pico)\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\tmenu_freeplay_song = menu.select;",
        "Pico Freeplay launch",
    )
    text = once(
        text,
        "\t\tmenu_fp_random_pick = (u8)RandomRange(0, MENU_FP_SONG_COUNT - 1);",
        "\t\tmenu_fp_random_pick = (u8)RandomRange(0, Menu_FreeplaySongCount() - 1);",
        "Pico random range",
    )
    text = once(
        text,
        "\tif (next < 0)\n"
        "\t\tnext = MENU_FP_OPTION_COUNT - 1;\n"
        "\telse if (next >= MENU_FP_OPTION_COUNT)\n"
        "\t\tnext = 0;",
        "\tu8 count = Menu_FreeplayOptionCount();\n"
        "\tif (next < 0)\n"
        "\t\tnext = count - 1;\n"
        "\telse if (next >= count)\n"
        "\t\tnext = 0;",
        "Pico dynamic navigation",
    )
    text = text.replace("MENU_FP_OPTION_COUNT", "Menu_FreeplayOptionCount()")
    text = once(
        text,
        "\tmenu_dj_frames = IO_Read(\"\\\\MENU\\\\FPDJ.BIN;1\");",
        "\tmenu_dj_frames = IO_Read(menu_freeplay_player == MenuPlayer_Pico ? \"\\\\MENU\\\\FPPICO.BIN;1\" : \"\\\\MENU\\\\FPDJ.BIN;1\");",
        "Pico DJ stream",
    )
    text = once(
        text,
        "\tframe %= MENU_DJ_FRAME_COUNT;",
        "\tframe %= (menu_freeplay_player == MenuPlayer_Pico ? 42 : MENU_DJ_FRAME_COUNT);",
        "Pico DJ frame count",
    )
    text = once(
        text,
        '\t\tback_path  = "\\\\MENU\\\\FPBG.TIM;1";\n'
        '\t\tng_path    = "\\\\MENU\\\\FPEXTRA.TIM;1";\n'
        '\t\tstory_path = "\\\\MENU\\\\FPUI.TIM;1";\n'
        '\t\ttitle_path = "\\\\MENU\\\\FPCHAR.TIM;1";',
        '\t\tback_path  = menu_freeplay_player == MenuPlayer_Pico ? "\\\\MENU\\\\FPBGP.TIM;1" : "\\\\MENU\\\\FPBG.TIM;1";\n'
        '\t\tng_path    = "\\\\MENU\\\\FPEXTRA.TIM;1";\n'
        '\t\tstory_path = "\\\\MENU\\\\FPUI.TIM;1";\n'
        '\t\ttitle_path = menu_freeplay_player == MenuPlayer_Pico ? "\\\\MENU\\\\FPPICO.TIM;1" : "\\\\MENU\\\\FPCHAR.TIM;1";',
        "Pico Freeplay textures",
    )
    text = once(
        text,
        '\t\tGfx_LoadTex(&menu_fp_anim, IO_Read("\\\\MENU\\\\FPANIM.TIM;1"), GFX_LOADTEX_FREE);',
        '\t\tGfx_LoadTex(&menu_fp_anim, IO_Read(menu_freeplay_player == MenuPlayer_Pico ? "\\\\MENU\\\\FPANIMP.TIM;1" : "\\\\MENU\\\\FPANIM.TIM;1"), GFX_LOADTEX_FREE);',
        "Pico Freeplay UI",
    )
    text = once(
        text,
        "u8 dj_frame = (u8)(((animf_count * 2) / 5) % MENU_DJ_FRAME_COUNT);",
        "u8 dj_frame = (u8)(((animf_count * 2) / 5) % (menu_freeplay_player == MenuPlayer_Pico ? 42 : MENU_DJ_FRAME_COUNT));",
        "Pico DJ animation",
    )
    menu.write_text(text)


def apply_character_select(menu: Path) -> None:
    text = menu.read_text()
    text = once(
        text,
        '#include "charselect_v7_1_generated.h"\n',
        '#include "charselect_v7_1_generated.h"\n#include "charselect_pico_generated.h"\n',
        "Pico Character Select header",
    )
    text = once(
        text,
        "static IO_Data menu_cs_char_frames = NULL;",
        "static IO_Data menu_cs_char_frames = NULL;\nstatic boolean menu_cs_pico_visuals = false;",
        "Pico Character Select bank state declaration",
    )
    text = once(
        text,
        '\tmenu_cs_char_frames = IO_Read("\\\\MENU\\\\CSCHAR8.RLE;1");',
        '\tmenu_cs_char_frames = IO_Read("\\\\MENU\\\\CSCHAR8.RLE;1");\n\tmenu_cs_pico_visuals = false;',
        "Pico Character Select default bank state",
    )
    helper_anchor = "static s32 menu_cs_v7_cursor_main_x = 0;"
    helpers = r'''static void Menu_LoadCSPlayerVisuals(boolean pico)
{
	if (menu_cs_pico_visuals == pico)
		return;
	if (menu_cs_char_frames != NULL)
		Mem_Free(menu_cs_char_frames);
	menu_cs_char_frames = IO_Read(pico ? "\\MENU\\CSPICO.RLE;1" : "\\MENU\\CSCHAR8.RLE;1");
	IO_Data c0 = IO_Read(pico ? "\\MENU\\CSPC71A.TIM;1" : "\\MENU\\CSC71A.TIM;1");
	IO_Data c1 = IO_Read(pico ? "\\MENU\\CSPC71B.TIM;1" : "\\MENU\\CSC71B.TIM;1");
	if (menu_cs_char_frames == NULL || c0 == NULL || c1 == NULL)
	{
		if (c0 != NULL) Mem_Free(c0);
		if (c1 != NULL) Mem_Free(c1);
		sprintf(error_msg, "[Menu_LoadCSPlayerVisuals] Pico Character Select asset missing");
		ErrorLock();
		return;
	}
	Gfx_LoadTex(&menu_cs_ctrl_v7[0], c0, GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu_cs_ctrl_v7[1], c1, GFX_LOADTEX_FREE);
	menu_cs_uploaded_char_frame = 0xFF;
	menu_cs_pico_visuals = pico;
}

'''
    text = once(text, helper_anchor, helpers + helper_anchor, "Pico Character Select loader")
    text = once(
        text,
        "static void Menu_CSDrawV71Locks(u8 state)\n"
        "{\n"
        "\tfor (u8 i=0;i<9;i++)\n"
        "\t{\n"
        "\t\tif (i==4) continue;",
        "static void Menu_CSDrawV71Locks(u8 state)\n"
        "{\n"
        "\tfor (u8 i=0;i<9;i++)\n"
        "\t{\n"
        "\t\tif (i==3 || i==4) continue;",
        "unlock Pico grid cell",
    )
    text = once(
        text,
        "\tRECT name_src,name_dst;\n"
        "\tif (state==4)\n"
        "\t{\n"
        "\t\tname_src=(RECT){CSV71_NAME_BF_X,CSV71_NAME_BF_Y,CSV71_NAME_BF_W,CSV71_NAME_BF_H};\n"
        "\t\tname_dst=(RECT){CSV71_NAME_BF_DST_X,CSV71_NAME_BF_DST_Y,CSV71_NAME_BF_W,CSV71_NAME_BF_H};\n"
        "\t}\n"
        "\telse\n"
        "\t{\n"
        "\t\tname_src=(RECT){CSV71_NAME_LOCKED_X,CSV71_NAME_LOCKED_Y,CSV71_NAME_LOCKED_W,CSV71_NAME_LOCKED_H};\n"
        "\t\tname_dst=(RECT){CSV71_NAME_LOCKED_DST_X,CSV71_NAME_LOCKED_DST_Y,CSV71_NAME_LOCKED_W,CSV71_NAME_LOCKED_H};\n"
        "\t}",
        "\tRECT name_src,name_dst;\n"
        "\tif (state==3)\n"
        "\t{\n"
        "\t\tname_src=(RECT){CSPICO_NAME_X,CSPICO_NAME_Y,CSPICO_NAME_W,CSPICO_NAME_H};\n"
        "\t\tname_dst=(RECT){CSPICO_NAME_DST_X,CSPICO_NAME_DST_Y,CSPICO_NAME_W,CSPICO_NAME_H};\n"
        "\t}\n"
        "\telse if (state==4)\n"
        "\t{\n"
        "\t\tname_src=(RECT){CSV71_NAME_BF_X,CSV71_NAME_BF_Y,CSV71_NAME_BF_W,CSV71_NAME_BF_H};\n"
        "\t\tname_dst=(RECT){CSV71_NAME_BF_DST_X,CSV71_NAME_BF_DST_Y,CSV71_NAME_BF_W,CSV71_NAME_BF_H};\n"
        "\t}\n"
        "\telse\n"
        "\t{\n"
        "\t\tname_src=(RECT){CSV71_NAME_LOCKED_X,CSV71_NAME_LOCKED_Y,CSV71_NAME_LOCKED_W,CSV71_NAME_LOCKED_H};\n"
        "\t\tname_dst=(RECT){CSV71_NAME_LOCKED_DST_X,CSV71_NAME_LOCKED_DST_Y,CSV71_NAME_LOCKED_W,CSV71_NAME_LOCKED_H};\n"
        "\t}",
        "Pico Character Select nametag",
    )
    text = once(
        text,
        "\tRECT is;\n"
        "\tif (menu_cs_mode==MenuCS_Confirm && state==4) is=(RECT){CSV71_ICON_CONFIRM_X,CSV71_ICON_CONFIRM_Y,CSV71_ICON_CONFIRM_W,CSV71_ICON_CONFIRM_H};\n"
        "\telse {u8 f=(u8)((animf_count/6)%CSV71_ICON_IDLE_COUNT); is=(RECT){csv71_icon_src_x[f],csv71_icon_src_y[f],CSV71_ICON_IDLE_0_W,CSV71_ICON_IDLE_0_H};}\n"
        "\tRECT id=(state==4)?(RECT){CSV71_ICON_SEL_X,CSV71_ICON_SEL_Y,CSV71_ICON_SEL_W,CSV71_ICON_SEL_H}:(RECT){CSV71_ICON_UNSEL_X,CSV71_ICON_UNSEL_Y,CSV71_ICON_UNSEL_W,CSV71_ICON_UNSEL_H};",
        "\tRECT is,id;\n"
        "\tif (state==3)\n"
        "\t{\n"
        "\t\tif (menu_cs_mode==MenuCS_Confirm) is=(RECT){CSPICO_ICON_CONFIRM_X,CSPICO_ICON_CONFIRM_Y,CSPICO_ICON_CONFIRM_W,CSPICO_ICON_CONFIRM_H};\n"
        "\t\telse {u8 f=(u8)((animf_count/6)%CSPICO_ICON_IDLE_COUNT); is=(RECT){cspico_icon_src_x[f],cspico_icon_src_y[f],CSPICO_ICON_IDLE_0_W,CSPICO_ICON_IDLE_0_H};}\n"
        "\t\tid=(RECT){CSPICO_ICON_SEL_X,CSPICO_ICON_SEL_Y,CSPICO_ICON_SEL_W,CSPICO_ICON_SEL_H};\n"
        "\t}\n"
        "\telse\n"
        "\t{\n"
        "\t\tif (menu_cs_mode==MenuCS_Confirm && state==4) is=(RECT){CSV71_ICON_CONFIRM_X,CSV71_ICON_CONFIRM_Y,CSV71_ICON_CONFIRM_W,CSV71_ICON_CONFIRM_H};\n"
        "\t\telse {u8 f=(u8)((animf_count/6)%CSV71_ICON_IDLE_COUNT); is=(RECT){csv71_icon_src_x[f],csv71_icon_src_y[f],CSV71_ICON_IDLE_0_W,CSV71_ICON_IDLE_0_H};}\n"
        "\t\tid=(state==4)?(RECT){CSV71_ICON_SEL_X,CSV71_ICON_SEL_Y,CSV71_ICON_SEL_W,CSV71_ICON_SEL_H}:(RECT){CSV71_ICON_UNSEL_X,CSV71_ICON_UNSEL_Y,CSV71_ICON_UNSEL_W,CSV71_ICON_UNSEL_H};\n"
        "\t}",
        "Pico Character Select icon",
    )
    # The Character Select state machine has two unlocked checks: selection
    # permission and the live character animation route.
    unlocked = "menu_cs_grid == 4"
    if text.count(unlocked) < 2:
        raise SystemExit(f"Pico Character Select unlock checks changed: {text.count(unlocked)}")
    text = text.replace(unlocked, "(menu_cs_grid == 4 || menu_cs_grid == 3)")
    text = once(
        text,
        "\t\t\t\t\t\tmenu_cs_grid = Menu_CSGridIndex();\n"
        "\t\t\t\t\t\tmenu_cs_timer = 0;",
        "\t\t\t\t\t\tmenu_cs_grid = Menu_CSGridIndex();\n"
        "\t\t\t\t\t\tMenu_LoadCSPlayerVisuals(menu_cs_grid == 3);\n"
        "\t\t\t\t\t\tmenu_cs_timer = 0;",
        "Pico Character Select movement swap",
    )
    text = once(
        text,
        "\t\t\t\tmenu_cs_x = 0;\n"
        "\t\t\t\tmenu_cs_y = 0;\n"
        "\t\t\t\tmenu_cs_grid = 4;\n"
        "\t\t\t\tmenu_cs_timer = 0;",
        "\t\t\t\tmenu_cs_x = menu_freeplay_player == MenuPlayer_Pico ? -1 : 0;\n"
        "\t\t\t\tmenu_cs_y = 0;\n"
        "\t\t\t\tmenu_cs_grid = menu_freeplay_player == MenuPlayer_Pico ? 3 : 4;\n"
        "\t\t\t\tMenu_LoadCSPlayerVisuals(menu_cs_grid == 3);\n"
        "\t\t\t\tmenu_cs_timer = 0;",
        "Pico Character Select initial bank",
    )
    text = once(
        text,
        "\t\t\t\t\tmenu_freeplay_player = MenuPlayer_Boyfriend;",
        "\t\t\t\t\tmenu_freeplay_player = menu_cs_grid == 3 ? MenuPlayer_Pico : MenuPlayer_Boyfriend;",
        "Pico Character Select confirmation",
    )
    menu.write_text(text)


def apply_stage(root: Path) -> None:
    stage_h = root / "src/stage.h"
    ids = "\n".join(f"\tStageId_PM_{key}, //{display} Pico Mix" for key, display, *_ in SONGS)
    replace_file(
        stage_h,
        "\tStageId_SF_1, //SPAGHETTI\n\n\tStageId_Max",
        "\tStageId_SF_1, //SPAGHETTI\n\n" + ids + "\n\n\tStageId_Max",
        "Pico StageIds",
    )

    stage = root / "src/stage.c"
    text = stage.read_text()
    text = once(text, '#include "stage/sserafim.h"\n', '#include "stage/sserafim.h"\n#include "stage/picomix.h"\n', "Pico stage include")
    character_headers = (
        '#include "character/picodark.h"\n#include "character/picoxmas.h"\n'
        '#include "character/picopixel.h"\n#include "character/picohold.h"\n'
        '#include "character/nenedark.h"\n#include "character/nenexmas.h"\n'
        '#include "character/nenepixel.h"\n#include "character/spookydark.h"\n'
        '#include "character/tankbloody.h"\n#include "character/otis.h"\n'
    )
    text = once(text, '#include "character/sfgf.h"\n', '#include "character/sfgf.h"\n' + character_headers, "Pico character includes")
    if text.count("!Sserafim_ApplyHit(note)") != 2:
        raise SystemExit("Pico hit hook: Sserafim anchor count changed")
    text = text.replace("!Sserafim_ApplyHit(note)", "!Sserafim_ApplyHit(note) && !PicoMix_ApplyHit(note)")
    if text.count("Sserafim_ApplyMiss(note);") != 2:
        raise SystemExit("Pico miss hook: Sserafim anchor count changed")
    text = re.sub(
        r"(?m)^(\s*)Sserafim_ApplyMiss\(note\);$",
        r"\1Sserafim_ApplyMiss(note);\n\1PicoMix_ApplyMiss(note);",
        text,
    )
    miss_line = "stage.player->set_anim(stage.player, note_anims[type][1]);"
    if text.count(miss_line) != 2:
        raise SystemExit(f"Pico direct miss hooks: expected two, found {text.count(miss_line)}")
    text = re.sub(
        r"(?m)^(\s*)stage\.player->set_anim\(stage\.player, note_anims\[type\]\[1\]\);$",
        r"\1if (!PicoMix_PlayMissDirection(type))\n\1\tstage.player->set_anim(stage.player, note_anims[type][1]);",
        text,
    )
    text = once(
        text,
        "\tWeekend1_Reset(id);\n\tSserafim_Reset(id);\n\tWeekend1_PlayIntro(id, story);\n\tSserafim_PlayIntro(id);",
        "\tWeekend1_Reset(id);\n\tSserafim_Reset(id);\n\tPicoMix_Reset(id);\n"
        "\tWeekend1_PlayIntro(id, story);\n\tSserafim_PlayIntro(id);\n\tPicoMix_PlayIntro(id);",
        "Pico load reset",
    )
    text = once(
        text,
        "\tStage_LoadMusic();\n\tif (Weekend1_BeginInGameIntro(id, story))",
        "\tStage_LoadMusic();\n\tPicoMix_Start();\n\tif (Weekend1_BeginInGameIntro(id, story))",
        "Pico runtime start",
    )
    text = once(
        text,
        "\t\t\t\tif (Weekend1_PlayEnding())",
        "\t\t\t\tPicoMix_PlayEnding();\n\t\t\t\tif (Weekend1_PlayEnding())",
        "Pico Stress ending",
    )
    text = once(
        text,
        "\t\t\t\tWeekend1_ExitStory();\n\t\t\t\tSserafim_Exit();",
        "\t\t\t\tWeekend1_ExitStory();\n\t\t\t\tSserafim_Exit();\n\t\t\t\tPicoMix_Exit();",
        "Pico cutscene session exit",
    )
    text = re.sub(r"(?m)^(\s*)Sserafim_ApplyCameraTarget\(\);$", r"\1Sserafim_ApplyCameraTarget();\n\1PicoMix_ApplyCameraTarget();", text)
    text = re.sub(r"(?m)^(\s*)Sserafim_ApplyCameraZoom\(\);$", r"\1Sserafim_ApplyCameraZoom();\n\1PicoMix_ApplyCameraZoom();", text)
    pause_anchor = '\t\t"SPAGHETTI",\n'
    pause_names = "".join(f'\t\t"{display}",\n' for _key, display, *_ in SONGS)
    text = once(text, pause_anchor, pause_anchor + pause_names, "Pico pause names")
    text = once(
        text,
        "\t\t\tif (!Sserafim_DrawHealthIcon(-1)) Stage_DrawHealth(stage.opponent->health_i, -1);",
        "\t\t\tif (!Sserafim_DrawHealthIcon(-1) && !PicoMix_DrawHealthIcon(-1)) Stage_DrawHealth(stage.opponent->health_i, -1);",
        "Pico bloody Tankman health icon",
    )
    stage.write_text(text)


def apply_audio(root: Path) -> None:
    audio_h = root / "src/audio.h"
    text = audio_h.read_text()
    text = once(
        text,
        "\tXA_Sserafim, //SPAG.XA\n\t\n\tXA_Max",
        "\tXA_Sserafim, //SPAG.XA\n"
        "\tXA_PicoMix0, //PICOMIX0.XA\n\tXA_PicoMix1, //PICOMIX1.XA\n"
        "\tXA_PicoMix2, //PICOMIX2.XA\n\tXA_PicoMix3, //PICOMIX3.XA\n\t\n\tXA_Max",
        "Pico XA files",
    )
    tracks = "\n".join(f"\tXA_PM_{key}," for key, *_ in SONGS)
    text = once(text, "\tXA_Spaghetti,\n} XA_Track;", "\tXA_Spaghetti,\n" + tracks + "\n} XA_Track;", "Pico XA tracks")
    audio_h.write_text(text)

    audio_c = root / "src/audio.c"
    text = audio_c.read_text()
    text = once(text, '#include "sserafim_audio_generated.h"\n', '#include "sserafim_audio_generated.h"\n#include "pico_mix_audio_generated.h"\n', "Pico audio header")
    rows = []
    for index, (key, *_rest) in enumerate(SONGS):
        rows.append(f"\t{{XA_PicoMix{index // 4}, XA_LENGTH(PICO_MIX_LENGTH_{index})}}, //XA_PM_{key}")
    text = once(
        text,
        "\t{XA_Sserafim, XA_LENGTH(SSERAFIM_XA_CENTISECONDS)}, //XA_Spaghetti\n};",
        "\t{XA_Sserafim, XA_LENGTH(SSERAFIM_XA_CENTISECONDS)}, //XA_Spaghetti\n"
        + "\n".join(rows) + "\n};",
        "Pico XA lengths",
    )
    paths = "".join(f'\t\t"\\\\MUSIC\\\\PICOMIX{i}.XA;1", //XA_PicoMix{i}\n' for i in range(4))
    text = once(
        text,
        '\t\t"\\\\MUSIC\\\\SPAG.XA;1",   //XA_Sserafim\n',
        '\t\t"\\\\MUSIC\\\\SPAG.XA;1",   //XA_Sserafim\n' + paths,
        "Pico XA paths",
    )
    audio_c.write_text(text)


def apply_definitions(root: Path) -> None:
    path = root / "src/stagedef_disc1.h"
    text = path.read_text()
    definitions = []
    for index, (key, _display, original, _track, _bpm) in enumerate(SONGS):
        definitions.append(pico_definition(text, index, key, original))
    base = text.rstrip()
    separator = "\n" if base.endswith(",") else ",\n"
    path.write_text(base + separator + ",\n".join(definitions) + "\n")


def apply_makefile(root: Path) -> None:
    makefile = root / "Makefile"
    text = makefile.read_text()
    text = once(text, "       src/stage/sserafim.c \\\n", "       src/stage/sserafim.c \\\n       src/stage/picomix.c \\\n", "Pico stage build")
    additions = "".join(
        f"       src/character/{name}.c \\\n"
        for name in ("picodark", "picoxmas", "picopixel", "picohold", "nenedark",
                     "nenexmas", "nenepixel", "spookydark", "tankbloody", "otis")
    )
    text = once(text, "       src/character/sfgf.c \\\n", "       src/character/sfgf.c \\\n" + additions, "Pico character build")
    makefile.write_text(text)


def apply_xml(root: Path) -> None:
    path = root / "funkin.xml"
    text = path.read_text()
    chart_lines = []
    for index in range(15):
        for suffix in ("e", "n", "h"):
            chart_lines.append(
                f'\t\t\t\t<file name = "10.{index + 1}{suffix}.cht" type = "data" '
                f'source = "iso/chart/10.{index + 1}{suffix}.cht"/>'
            )
    charts = '\t\t\t<!-- Official Pico Mix charts -->\n\t\t\t<dir name = "week10">\n' + "\n".join(chart_lines) + "\n\t\t\t</dir>\n\n"
    text = once(text, "\t\t\t<!-- Kapi assets -->", charts + "\t\t\t<!-- Kapi assets -->", "Pico chart XML")
    character_files = (
        "picodark.arc", "picoxmas.arc", "picohold.arc", "picopix.arc",
        "nenedark.arc", "nenexmas.arc", "nenepix.arc", "spookydk.arc",
        "tankbldy.arc", "otis.arc",
    )
    char_xml = "".join(f'\t\t\t\t<file name = "{name}" type = "data" source = "iso/{name}"/>\n' for name in character_files)
    text = once(
        text,
        '\t\t\t\t<file name = "sfgf.arc" type = "data" source = "iso/sfgf.arc"/>\n',
        '\t\t\t\t<file name = "sfgf.arc" type = "data" source = "iso/sfgf.arc"/>\n' + char_xml,
        "Pico character XML",
    )
    audio_xml = "".join(f'\t\t\t\t<file name = "picomix{i}.xa" type = "xa" source = "iso/music/picomix{i}.xa"/>\n' for i in range(4))
    text = once(
        text,
        '\t\t\t\t<file name = "spag.xa" type = "xa" source = "iso/music/spag.xa"/>\n',
        '\t\t\t\t<file name = "spag.xa" type = "xa" source = "iso/music/spag.xa"/>\n' + audio_xml,
        "Pico audio XML",
    )
    menu_files = ("fppico.bin", "fppico.tim", "fpbgp.tim", "fpanimp.tim", "cspico.rle", "cspc71a.tim", "cspc71b.tim")
    menu_xml = "".join(f'\t\t\t\t<file name = "{name}" type = "data" source = "iso/menu/{name}"/>\n' for name in menu_files)
    text = once(
        text,
        '\t\t\t\t<file name = "fpmeta.tim" type = "data" source = "iso/menu/fpmeta.tim"/>\n',
        '\t\t\t\t<file name = "fpmeta.tim" type = "data" source = "iso/menu/fpmeta.tim"/>\n' + menu_xml,
        "Pico menu XML",
    )
    text = once(
        text,
        '\t\t\t\t<file name = "sfend.str" type = "xa" source = "iso/movie/sfend.str"/>\n',
        '\t\t\t\t<file name = "sfend.str" type = "xa" source = "iso/movie/sfend.str"/>\n'
        '\t\t\t\t<file name = "pstrs.str" type = "xa" source = "iso/movie/pstrs.str"/>\n'
        '\t\t\t\t<file name = "pstrend.str" type = "xa" source = "iso/movie/pstrend.str"/>\n',
        "Pico stress movie XML",
    )
    text = once(
        text,
        '\t\t\t\t<file name = "hud1.tim" type = "data" source = "iso/stage/hud1.tim"/>\n',
        '\t\t\t\t<file name = "hud1.tim" type = "data" source = "iso/stage/hud1.tim"/>\n'
        '\t\t\t\t<file name = "pmblood.tim" type = "data" source = "iso/stage/pmblood.tim"/>\n',
        "Pico bloody Tankman health icon XML",
    )
    path.write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    root = args.upstream
    (root / "src/stage/picomix.h").write_text(PICO_H)
    (root / "src/stage/picomix.c").write_text(PICO_C)
    apply_makefile(root)
    apply_stage(root)
    apply_audio(root)
    apply_definitions(root)
    apply_freeplay(root / "src/menu.c")
    apply_character_select(root / "src/menu.c")
    apply_xml(root)
    fallback = Path(__file__).with_name("apply_iso9660_lookup_fallback.py")
    subprocess.run(
        [sys.executable, str(fallback), "--upstream", str(root)],
        check=True,
    )
    print("Applied all 15 official Pico Mixes, Pico Freeplay routing, runtime events, and ISO9660 lookup fallback")


if __name__ == "__main__":
    main()
