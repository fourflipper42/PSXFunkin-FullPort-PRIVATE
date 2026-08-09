#!/usr/bin/env python3
"""Apply missing Week 2/5/6 stages and characters to the cuckydev baseline."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


def copy_adapted(reference: Path, destination: Path) -> None:
    text = reference.read_text()
    text = re.sub(r"\n\s*this->character\.spec = [^;]+;\n", "\n", text)
    text = text.replace(
        "Character_DrawParallax(character, &this->tex, &char_xmasgf_frame[this->frame], parallax);",
        "Character_Draw(character, &this->tex, &char_xmasgf_frame[this->frame]);",
    )
    text = text.replace(
        "Character_DrawParallax(character, &this->tex, &char_gfweeb_frame[this->frame], parallax);",
        "Character_Draw(character, &this->tex, &char_gfweeb_frame[this->frame]);",
    )
    text = text.replace(
        "Speaker_Tick(&this->speaker, character->x, character->y, parallax);",
        "Speaker_Tick(&this->speaker, character->x, character->y);",
    )
    text = text.replace('#include "gf.h"', '#include "gfweeb.h"')
    text = text.replace("\tXmasBF_ArcMain_XmasBF6,\n", "")
    text = text.replace("if(stage.prefs.lowquality ==false)", "if (1)")
    text = text.replace("if (stage.prefs.lowquality ==false)", "if (1)")
    text = text.replace("character->pad_held", "pad_state.held")
    if destination.name == "xmasbf.c":
        # The conversion reference uses four standalone PlayerAnim_*Miss enum
        # values. cuckydev t0.12 stores the same miss poses in the standard
        # CharAnim_*Alt slots, exactly like its native Boyfriend module. Move
        # the authentic Christmas miss scripts into those slots and remove the
        # four reference-only array entries so PlayerAnim_Peace/death indices
        # retain the engine ABI expected by stage.c.
        text = text.replace(
            "\t{0, (const u8[]){ASCR_CHGANI, CharAnim_Idle}},       //CharAnim_LeftAlt\n",
            "\t{1, (const u8[]){ 5, 13, 13, 14, ASCR_BACK, 1}},     //CharAnim_LeftAlt / miss\n",
        )
        text = text.replace(
            "\t{0, (const u8[]){ASCR_CHGANI, CharAnim_Idle}},       //CharAnim_DownAlt\n",
            "\t{1, (const u8[]){ 7, 15, 15, 16, ASCR_BACK, 1}},     //CharAnim_DownAlt / miss\n",
        )
        text = text.replace(
            "\t{0, (const u8[]){ASCR_CHGANI, CharAnim_Idle}},       //CharAnim_UpAlt\n",
            "\t{1, (const u8[]){ 9, 17, 17, 18, ASCR_BACK, 1}},     //CharAnim_UpAlt / miss\n",
        )
        text = text.replace(
            "\t{0, (const u8[]){ASCR_CHGANI, CharAnim_Idle}},       //CharAnim_RightAlt\n",
            "\t{1, (const u8[]){11, 19, 19, 20, ASCR_BACK, 1}},     //CharAnim_RightAlt / miss\n",
        )
        text = re.sub(
            r"\n\s*\{1, \(const u8\[\]\)\{ 5, 13, 13, 14, ASCR_BACK, 1\}\},\s*//PlayerAnim_LeftMiss\n"
            r"\s*\{1, \(const u8\[\]\)\{ 7, 15, 15, 16, ASCR_BACK, 1\}\},\s*//PlayerAnim_DownMiss\n"
            r"\s*\{1, \(const u8\[\]\)\{ 9, 17, 17, 18, ASCR_BACK, 1\}\},\s*//PlayerAnim_UpMiss\n"
            r"\s*\{1, \(const u8\[\]\)\{11, 19, 19, 20, ASCR_BACK, 1\}\},\s*//PlayerAnim_RightMiss\n",
            "\n",
            text,
        )
        text = text.replace("PlayerAnim_LeftMiss", "CharAnim_LeftAlt")
        text = text.replace("PlayerAnim_DownMiss", "CharAnim_DownAlt")
        text = text.replace("PlayerAnim_UpMiss", "CharAnim_UpAlt")
        text = text.replace("PlayerAnim_RightMiss", "CharAnim_RightAlt")
    text = text.replace(
        "\t//Perform idle dance\n"
        "\tif ((pad_state.held & (INPUT_LEFT | INPUT_DOWN | INPUT_UP | INPUT_RIGHT)) == 0)\n"
        "\t\tCharacter_PerformIdle(character);\n",
        "\t//Use the cuckydev character idle contract.\n"
        "\tCharacter_CheckEndSing(character);\n"
        "\tif ((stage.flag & STAGE_FLAG_JUST_STEP) && Animatable_Ended(&character->animatable) &&\n"
        "\t    character->animatable.anim != CharAnim_Left && character->animatable.anim != CharAnim_Down &&\n"
        "\t    character->animatable.anim != CharAnim_Up && character->animatable.anim != CharAnim_Right &&\n"
        "\t    (stage.song_step & 0x7) == 0)\n"
        "\t\tcharacter->set_anim(character, CharAnim_Idle);\n",
    )
    text = re.sub(
        r"\n\s*stage\.bgcolor\[0\]=([0-9]+);\n\s*stage\.bgcolor\[1\]=([0-9]+);\n\s*stage\.bgcolor\[2\]=([0-9]+);\n\s*Gfx_SetClear\(stage\.bgcolor\[0\], stage\.bgcolor\[1\], stage\.bgcolor\[2\]\);",
        lambda match: f"\n\tGfx_SetClear({match.group(1)}, {match.group(2)}, {match.group(3)});",
        text,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text)


COMPACT_XMASP_SOURCE = r'''/*
  This Source Code Form is subject to the terms of the Mozilla Public
  License, v. 2.0. If a copy of the MPL was not distributed with this
  file, You can obtain one at http://mozilla.org/MPL/2.0/.

  PS1 RAM adaptation: all twenty authentic frames are packed four per page at
  half resolution and drawn at 2x. Animation content and offsets are retained.
*/

#include "xmasp.h"

#include "../mem.h"
#include "../archive.h"
#include "../stage.h"
#include "../main.h"

enum
{
	XmasP_ArcMain_Page0,
	XmasP_ArcMain_Page1,
	XmasP_ArcMain_Page2,
	XmasP_ArcMain_Page3,
	XmasP_ArcMain_Page4,
	XmasP_Arc_Max,
};

typedef struct
{
	Character character;
	IO_Data arc_main;
	IO_Data arc_ptr[XmasP_Arc_Max];
	Gfx_Tex tex;
	u8 frame, tex_id;
} Char_XmasP;

static const CharFrame char_xmasp_frame[] = {
	{0, {  0,   0, 110,  98}, {130, 182}},
	{0, {128,   0, 110,  96}, {131, 178}},
	{0, {  0, 128, 111,  96}, {130, 179}},
	{0, {128, 128, 109,  98}, {127, 183}},
	{1, {  0,   0,  99, 101}, {123, 188}},
	{1, {128,   0, 101, 101}, {125, 188}},
	{1, {  0, 128,  99, 100}, {122, 188}},
	{1, {128, 128, 101, 100}, {125, 188}},
	{2, {  0,   0, 107,  95}, {120, 177}},
	{2, {128,   0, 107,  95}, {122, 178}},
	{2, {  0, 128, 107,  95}, {121, 177}},
	{2, {128, 128, 107,  95}, {123, 178}},
	{3, {  0,   0, 100, 102}, {117, 190}},
	{3, {128,   0, 101, 102}, {120, 190}},
	{3, {  0, 128,  99, 102}, {117, 191}},
	{3, {128, 128, 101, 101}, {119, 190}},
	{4, {  0,   0, 120,  94}, {128, 174}},
	{4, {128,   0, 120,  96}, {130, 178}},
	{4, {  0, 128, 120,  95}, {128, 176}},
	{4, {128, 128, 120,  96}, {130, 178}},
};

static const Animation char_xmasp_anim[CharAnim_Max] = {
	{2, (const u8[]){ 0,  1,  2,  3, ASCR_BACK, 1}},
	{2, (const u8[]){ 4,  5, ASCR_BACK, 1}},
	{2, (const u8[]){ 6,  7, ASCR_BACK, 1}},
	{2, (const u8[]){ 8,  9, ASCR_BACK, 1}},
	{2, (const u8[]){10, 11, ASCR_BACK, 1}},
	{2, (const u8[]){12, 13, ASCR_BACK, 1}},
	{2, (const u8[]){14, 15, ASCR_BACK, 1}},
	{2, (const u8[]){16, 17, ASCR_BACK, 1}},
	{2, (const u8[]){18, 19, ASCR_BACK, 1}},
};

static void Char_XmasP_SetFrame(void *user, u8 frame)
{
	Char_XmasP *this = (Char_XmasP*)user;
	if (frame != this->frame)
	{
		const CharFrame *cframe = &char_xmasp_frame[this->frame = frame];
		if (cframe->tex != this->tex_id)
			Gfx_LoadTex(&this->tex, this->arc_ptr[this->tex_id = cframe->tex], 0);
	}
}

static void Char_XmasP_Draw2x(Char_XmasP *this)
{
	const CharFrame *cframe = &char_xmasp_frame[this->frame];
	fixed_t x = this->character.x - stage.camera.x - ((fixed_t)cframe->off[0] << FIXED_SHIFT);
	fixed_t y = this->character.y - stage.camera.y - ((fixed_t)cframe->off[1] << FIXED_SHIFT);
	RECT src = {cframe->src[0], cframe->src[1], cframe->src[2], cframe->src[3]};
	RECT_FIXED dst = {x, y, (src.w * 2) << FIXED_SHIFT, (src.h * 2) << FIXED_SHIFT};
	Stage_DrawTex(&this->tex, &src, &dst, stage.camera.bzoom);
}

static void Char_XmasP_Tick(Character *character)
{
	Char_XmasP *this = (Char_XmasP*)character;
	Character_CheckEndSing(character);
	if ((stage.flag & STAGE_FLAG_JUST_STEP) && Animatable_Ended(&character->animatable) &&
	    character->animatable.anim != CharAnim_Left && character->animatable.anim != CharAnim_Down &&
	    character->animatable.anim != CharAnim_Up && character->animatable.anim != CharAnim_Right &&
	    (stage.song_step & 0x7) == 0)
		character->set_anim(character, CharAnim_Idle);
	Animatable_Animate(&character->animatable, this, Char_XmasP_SetFrame);
	Char_XmasP_Draw2x(this);
}

static void Char_XmasP_SetAnim(Character *character, u8 anim)
{
	Animatable_SetAnim(&character->animatable, anim);
	Character_CheckStartSing(character);
}

static void Char_XmasP_Free(Character *character)
{
	Char_XmasP *this = (Char_XmasP*)character;
	Mem_Free(this->arc_main);
}

Character *Char_XmasP_New(fixed_t x, fixed_t y)
{
	Char_XmasP *this = Mem_Alloc(sizeof(Char_XmasP));
	if (this == NULL)
	{
		sprintf(error_msg, "[Char_XmasP_New] Failed to allocate Christmas Parents object");
		ErrorLock();
		return NULL;
	}
	this->character.tick = Char_XmasP_Tick;
	this->character.set_anim = Char_XmasP_SetAnim;
	this->character.free = Char_XmasP_Free;
	Animatable_Init(&this->character.animatable, char_xmasp_anim);
	Character_Init((Character*)this, x, y);
	this->character.health_i = 6;
	this->character.focus_x = FIXED_DEC(25,1);
	this->character.focus_y = FIXED_DEC(-100,1);
	this->character.focus_zoom = FIXED_DEC(1,1);
	this->arc_main = IO_Read("\\CHAR\\XMASP.ARC;1");
	const char **pathp = (const char *[]){
		"xmasp0.tim", "xmasp1.tim", "xmasp2.tim", "xmasp3.tim", "xmasp4.tim", NULL
	};
	IO_Data *arc_ptr = this->arc_ptr;
	for (; *pathp != NULL; pathp++)
		*arc_ptr++ = Archive_Find(this->arc_main, *pathp);
	this->tex_id = this->frame = 0xFF;
	return (Character*)this;
}
'''


WEEK5_EVIL_RUNTIME = r'''

// Winter Horrorland background, composed only from official v0.8.4 sources.
typedef struct
{
	StageBack back;
	Gfx_Tex tex;
} Back_Week5Evil;

static void Back_Week5Evil_DrawBG(StageBack *back)
{
	Back_Week5Evil *this = (Back_Week5Evil*)back;
	RECT src = {0, 0, 256, 192};
	RECT_FIXED dst = {
		FIXED_DEC(-200,1) - stage.camera.x / 5,
		FIXED_DEC(-135,1) - stage.camera.y / 5,
		FIXED_DEC(400,1), FIXED_DEC(300,1)
	};
	Stage_DrawTex(&this->tex, &src, &dst, stage.camera.bzoom);
	Gfx_SetClear(35, 6, 45);
}

static void Back_Week5Evil_Free(StageBack *back)
{
	Mem_Free(back);
}

StageBack *Back_Week5Evil_New(void)
{
	Back_Week5Evil *this = (Back_Week5Evil*)Mem_Alloc(sizeof(Back_Week5Evil));
	if (this == NULL)
		return NULL;
	this->back.draw_fg = NULL;
	this->back.draw_md = NULL;
	this->back.draw_bg = Back_Week5Evil_DrawBG;
	this->back.free = Back_Week5Evil_Free;
	Gfx_LoadTex(&this->tex, IO_Read("\\WEEK5\\EVIL.TIM;1"), GFX_LOADTEX_FREE);
	return (StageBack*)this;
}
'''


def patch_week2(path: Path) -> None:
    once(path, '#include "../archive.h"\n', '#include "../archive.h"\n#include "../random.h"\n', "Week 2 random include")
    once(
        path,
        "\tGfx_Tex tex_back2; //Lightning window\n",
        "\tGfx_Tex tex_back2; //Lightning window\n\n\tu8 lightning_frames;\n\tu8 lightning_cooldown;\n",
        "Week 2 lightning state",
    )
    once(
        path,
        "\tfx = stage.camera.x;\n\tfy = stage.camera.y;\n\t\n\t//Draw window\n",
        "\tfx = stage.camera.x;\n\tfy = stage.camera.y;\n\n"
        "\tif ((stage.flag & STAGE_FLAG_JUST_STEP) && (stage.song_step & 3) == 0)\n"
        "\t{\n"
        "\t\tif (this->lightning_cooldown != 0)\n"
        "\t\t\tthis->lightning_cooldown--;\n"
        "\t\telse if (RandomRange(0, 9) == 0)\n"
        "\t\t{\n"
        "\t\t\tthis->lightning_frames = 6;\n"
        "\t\t\tthis->lightning_cooldown = RandomRange(8, 24);\n"
        "\t\t}\n"
        "\t}\n"
        "\tif (stage.state == StageState_Play && this->lightning_frames != 0)\n"
        "\t\tthis->lightning_frames--;\n\t\n\t//Draw window\n",
        "Week 2 lightning trigger",
    )
    once(
        path,
        "\tStage_DrawTex(&this->tex_back1, &window_src, &window_dst, stage.camera.bzoom);\n",
        "\tStage_DrawTex((this->lightning_frames != 0) ? &this->tex_back2 : &this->tex_back1, &window_src, &window_dst, stage.camera.bzoom);\n",
        "Week 2 lightning draw",
    )
    once(
        path,
        "\tMem_Free(arc_back);\n\t\n\treturn (StageBack*)this;\n",
        "\tMem_Free(arc_back);\n\tthis->lightning_frames = 0;\n\tthis->lightning_cooldown = 4;\n\t\n\treturn (StageBack*)this;\n",
        "Week 2 lightning initialization",
    )


def patch_stage_definitions(path: Path) -> None:
    text = path.read_text()
    regions = [
        ("\t{ //StageId_2_3", "\n\t{ //StageId_3_1", {
            "Char_Spook_New": "Char_Monster_New",
        }),
        ("\t{ //StageId_5_1", "\n\t{ //StageId_5_2", {
            "Char_BF_New": "Char_XmasBF_New",
            "Char_Dad_New": "Char_XmasP_New",
            "Char_GF_New": "Char_XmasGF_New",
            "Back_Dummy_New": "Back_Week5_New",
            "FIXED_DEC(105,1)": "FIXED_DEC(90,1)",
            "FIXED_DEC(-120,1)": "FIXED_DEC(-190,1)",
            "FIXED_DEC(100,1)": "FIXED_DEC(85,1)",
        }),
        ("\t{ //StageId_5_2", "\n\t{ //StageId_5_3", {
            "Char_BF_New": "Char_XmasBF_New",
            "Char_Dad_New": "Char_XmasP_New",
            "Char_GF_New": "Char_XmasGF_New",
            "Back_Dummy_New": "Back_Week5_New",
            "FIXED_DEC(105,1)": "FIXED_DEC(90,1)",
            "FIXED_DEC(-120,1)": "FIXED_DEC(-190,1)",
            "FIXED_DEC(100,1)": "FIXED_DEC(85,1)",
            "StageId_5_3, STAGE_LOAD_FLAG": "StageId_5_3, STAGE_LOAD_FLAG | STAGE_LOAD_OPPONENT | STAGE_LOAD_STAGE",
        }),
        ("\t{ //StageId_5_3", "\n\t{ //StageId_6_1", {
            "Char_BF_New": "Char_XmasBF_New",
            "Char_Dad_New": "Char_Monsterx_New",
            "Char_GF_New": "Char_XmasGF_New",
            "Back_Dummy_New": "Back_Week5Evil_New",
            "FIXED_DEC(105,1)": "FIXED_DEC(90,1)",
            "FIXED_DEC(-120,1)": "FIXED_DEC(-125,1)",
            "FIXED_DEC(100,1)": "FIXED_DEC(85,1)",
            "{Char_Monsterx_New, FIXED_DEC(-125,1),  FIXED_DEC(85,1)}": "{Char_Monsterx_New, FIXED_DEC(-125,1),  FIXED_DEC(70,1)}",
        }),
        ("\t{ //StageId_6_1", "\n\t{ //StageId_6_2", {
            "{Char_BFWeeb_New,   FIXED_DEC(0,1),  FIXED_DEC(-8,1)}": "{Char_GFWeeb_New,   FIXED_DEC(0,1),  FIXED_DEC(45,1)}",
            "Back_Dummy_New": "Back_Week6_New",
        }),
        ("\t{ //StageId_6_2", "\n\t{ //StageId_6_3", {
            "Char_Senpai_New": "Char_SenpaiM_New",
            "{Char_BFWeeb_New,   FIXED_DEC(0,1),  FIXED_DEC(-8,1)}": "{Char_GFWeeb_New,   FIXED_DEC(0,1),  FIXED_DEC(45,1)}",
            "Back_Dummy_New": "Back_Week6_New",
        }),
        ("\t{ //StageId_6_3", "\n\t{ //StageId_7_1", {
            "Char_Senpai_New": "Char_Spirit_New",
            "{Char_BFWeeb_New,   FIXED_DEC(0,1),  FIXED_DEC(-8,1)}": "{Char_GFWeeb_New,   FIXED_DEC(0,1),  FIXED_DEC(45,1)}",
            "Back_Dummy_New": "Back_Week6_New",
        }),
    ]
    for start, end, replacements in regions:
        start_at = text.find(start)
        end_at = text.find(end, start_at + 1)
        if start_at < 0 or end_at < 0:
            raise SystemExit(f"stage definition region missing: {start.strip()}")
        block = text[start_at:end_at]
        for old, new in replacements.items():
            if old not in block:
                raise SystemExit(f"stage definition anchor missing in {start.strip()}: {old}")
            block = block.replace(old, new)
        text = text[:start_at] + block + text[end_at:]
    path.write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--reference-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    reference = args.reference_root

    source_files = [
        "src/stage/week5.c", "src/stage/week5.h",
        "src/stage/week6.c", "src/stage/week6.h",
        "src/character/monster.c", "src/character/monster.h",
        "src/character/xmasbf.c", "src/character/xmasbf.h",
        "src/character/xmasgf.c", "src/character/xmasgf.h",
        "src/character/xmasp.h",
        "src/character/monsterx.c", "src/character/monsterx.h",
        "src/character/gfweeb.c", "src/character/gfweeb.h",
        "src/character/senpaim.c", "src/character/senpaim.h",
        "src/character/spirit.c", "src/character/spirit.h",
    ]
    for relative in source_files:
        copy_adapted(reference / relative, root / relative)
    (root / "src/character/xmasp.c").write_text(COMPACT_XMASP_SOURCE)

    week5_c = root / "src/stage/week5.c"
    week5_c.write_text(week5_c.read_text() + WEEK5_EVIL_RUNTIME)
    once(
        root / "src/stage/week5.h",
        "StageBack *Back_Week5_New();\n",
        "StageBack *Back_Week5_New();\nStageBack *Back_Week5Evil_New(void);\n",
        "Winter Horrorland constructor declaration",
    )
    once(
        week5_c,
        "\t//Draw Santa\n\t\n\t//Draw snow\n",
        "\t//Draw Santa with a small beat bounce.\n"
        "\tRECT santa_src = {0, 0, 180, 190};\n"
        "\tRECT_FIXED santa_dst = {FIXED_DEC(-90,1) - stage.camera.x, FIXED_DEC(-112,1) - stage.camera.y + (beat_bop << 2), FIXED_DEC(180,1), FIXED_DEC(190,1) - (beat_bop << 2)};\n"
        "\tStage_DrawTex(&this->tex_back3, &santa_src, &santa_dst, stage.camera.bzoom);\n\t\n\t//Draw snow\n",
        "Week 5 Santa draw",
    )

    patch_week2(root / "src/stage/week2.c")

    # Authentic Spirit ghost uses PS1 semi-transparent arbitrary quads.
    once(
        root / "src/gfx.h",
        "void Gfx_DrawTexArb(Gfx_Tex *tex, const RECT *src, const POINT *p0, const POINT *p1, const POINT *p2, const POINT *p3);\n",
        "void Gfx_DrawTexArb(Gfx_Tex *tex, const RECT *src, const POINT *p0, const POINT *p1, const POINT *p2, const POINT *p3);\n"
        "void Gfx_BlendTexArb(Gfx_Tex *tex, const RECT *src, const POINT *p0, const POINT *p1, const POINT *p2, const POINT *p3, u8 mode);\n",
        "arbitrary blend declaration",
    )
    gfx_c = root / "src/gfx.c"
    if gfx_c.read_text().count("void Gfx_DrawTexArb(") != 1 or "void Gfx_BlendTexArb(" in gfx_c.read_text():
        raise SystemExit("arbitrary blend runtime: unexpected graphics source state")
    gfx_c.write_text(
        gfx_c.read_text()
        + "\nvoid Gfx_BlendTexArb(Gfx_Tex *tex, const RECT *src, const POINT *p0, const POINT *p1, const POINT *p2, const POINT *p3, u8 mode)\n"
        "{\n"
        "\tPOLY_FT4 *quad = (POLY_FT4*)nextpri;\n"
        "\tsetPolyFT4(quad);\n"
        "\tsetUVWH(quad, src->x, src->y, src->w, src->h);\n"
        "\tsetXY4(quad, p0->x, p0->y, p1->x, p1->y, p2->x, p2->y, p3->x, p3->y);\n"
        "\tsetRGB0(quad, 0x80, 0x80, 0x80);\n"
        "\tsetSemiTrans(quad, 1);\n"
        "\tquad->tpage = tex->tpage | getTPage(0, mode & 3, 0, 0);\n"
        "\tquad->clut = tex->clut;\n"
        "\taddPrim(ot[db], quad);\n"
        "\tnextpri += sizeof(POLY_FT4);\n"
        "}\n"
    )
    once(
        root / "src/stage.h",
        "void Stage_DrawTexArb(Gfx_Tex *tex, const RECT *src, const POINT_FIXED *p0, const POINT_FIXED *p1, const POINT_FIXED *p2, const POINT_FIXED *p3, fixed_t zoom);\n",
        "void Stage_DrawTexArb(Gfx_Tex *tex, const RECT *src, const POINT_FIXED *p0, const POINT_FIXED *p1, const POINT_FIXED *p2, const POINT_FIXED *p3, fixed_t zoom);\n"
        "void Stage_BlendTexArb(Gfx_Tex *tex, const RECT *src, const POINT_FIXED *p0, const POINT_FIXED *p1, const POINT_FIXED *p2, const POINT_FIXED *p3, fixed_t zoom, u8 mode);\n",
        "stage blend declaration",
    )
    once(
        root / "src/stage.c",
        "\tGfx_DrawTexArb(tex, src, &s0, &s1, &s2, &s3);\n}\n\n//Stage HUD functions and constants\n",
        "\tGfx_DrawTexArb(tex, src, &s0, &s1, &s2, &s3);\n}\n\n"
        "void Stage_BlendTexArb(Gfx_Tex *tex, const RECT *src, const POINT_FIXED *p0, const POINT_FIXED *p1, const POINT_FIXED *p2, const POINT_FIXED *p3, fixed_t zoom, u8 mode)\n"
        "{\n"
        "\tPOINT s0 = {SCREEN_WIDTH2 + (FIXED_MUL(p0->x, zoom) >> FIXED_SHIFT), SCREEN_HEIGHT2 + (FIXED_MUL(p0->y, zoom) >> FIXED_SHIFT)};\n"
        "\tPOINT s1 = {SCREEN_WIDTH2 + (FIXED_MUL(p1->x, zoom) >> FIXED_SHIFT), SCREEN_HEIGHT2 + (FIXED_MUL(p1->y, zoom) >> FIXED_SHIFT)};\n"
        "\tPOINT s2 = {SCREEN_WIDTH2 + (FIXED_MUL(p2->x, zoom) >> FIXED_SHIFT), SCREEN_HEIGHT2 + (FIXED_MUL(p2->y, zoom) >> FIXED_SHIFT)};\n"
        "\tPOINT s3 = {SCREEN_WIDTH2 + (FIXED_MUL(p3->x, zoom) >> FIXED_SHIFT), SCREEN_HEIGHT2 + (FIXED_MUL(p3->y, zoom) >> FIXED_SHIFT)};\n"
        "\tGfx_BlendTexArb(tex, src, &s0, &s1, &s2, &s3, mode);\n"
        "}\n\n//Stage HUD functions and constants\n",
        "stage blend runtime",
    )

    stage_c = root / "src/stage.c"
    once(
        stage_c,
        '#include "character/spook.h"\n',
        '#include "character/spook.h"\n#include "character/monster.h"\n',
        "Monster include",
    )
    once(
        stage_c,
        '#include "character/mom.h"\n',
        '#include "character/mom.h"\n'
        '#include "character/xmasbf.h"\n#include "character/xmasgf.h"\n#include "character/xmasp.h"\n#include "character/monsterx.h"\n',
        "Week 5 character includes",
    )
    once(
        stage_c,
        '#include "character/senpai.h"\n',
        '#include "character/senpai.h"\n#include "character/gfweeb.h"\n#include "character/senpaim.h"\n#include "character/spirit.h"\n',
        "Week 6 character includes",
    )
    once(
        stage_c,
        '#include "stage/week4.h"\n',
        '#include "stage/week4.h"\n#include "stage/week5.h"\n#include "stage/week6.h"\n',
        "Week 5/6 stage includes",
    )

    patch_stage_definitions(root / "src/stagedef_disc1.h")

    makefile = root / "Makefile"
    once(
        makefile,
        "       src/stage/week4.c \\\n       src/stage/week7.c \\\n",
        "       src/stage/week4.c \\\n       src/stage/week5.c \\\n       src/stage/week6.c \\\n       src/stage/week7.c \\\n",
        "Week 5/6 Makefile sources",
    )
    once(
        makefile,
        "       src/character/spook.c \\\n       src/character/pico.c \\\n",
        "       src/character/spook.c \\\n       src/character/monster.c \\\n       src/character/pico.c \\\n",
        "Monster Makefile source",
    )
    once(
        makefile,
        "       src/character/mom.c \\\n       src/character/senpai.c \\\n",
        "       src/character/mom.c \\\n       src/character/xmasbf.c \\\n       src/character/xmasgf.c \\\n       src/character/xmasp.c \\\n       src/character/monsterx.c \\\n       src/character/senpai.c \\\n       src/character/gfweeb.c \\\n       src/character/senpaim.c \\\n       src/character/spirit.c \\\n",
        "Week 5/6 Makefile character sources",
    )

    xml = root / "funkin.xml"
    once(
        xml,
        '\t\t\t<dir name = "week5">\n\t\t\t\t<!-- Cocoa charts -->\n',
        '\t\t\t<dir name = "week5">\n'
        '\t\t\t\t<file name = "back.arc" type = "data" source = "iso/week5/back.arc"/>\n'
        '\t\t\t\t<file name = "evil.tim" type = "data" source = "iso/week5/evil.tim"/>\n\t\t\t\t<!-- Cocoa charts -->\n',
        "Week 5 disc assets",
    )
    once(
        xml,
        '\t\t\t<dir name = "week6">\n\t\t\t\t<!-- Senpai charts -->\n',
        '\t\t\t<dir name = "week6">\n'
        '\t\t\t\t<file name = "back.arc" type = "data" source = "iso/week6/back.arc"/>\n'
        '\t\t\t\t<file name = "back3.tim" type = "data" source = "iso/week6/back3.tim"/>\n\t\t\t\t<!-- Senpai charts -->\n',
        "Week 6 disc assets",
    )
    once(
        xml,
        '\t\t\t\t<file name = "spook.arc" type = "data" source = "iso/spook/main.arc"/>\n',
        '\t\t\t\t<file name = "spook.arc" type = "data" source = "iso/spook/main.arc"/>\n'
        '\t\t\t\t<file name = "monster.arc" type = "data" source = "iso/monster/main.arc"/>\n',
        "Monster disc asset",
    )
    once(
        xml,
        '\t\t\t\t<file name = "mom.arc" type = "data" source = "iso/mom/main.arc"/>\n',
        '\t\t\t\t<file name = "mom.arc" type = "data" source = "iso/mom/main.arc"/>\n'
        '\t\t\t\t<file name = "xmasbf.arc" type = "data" source = "iso/bf/xmas.arc"/>\n'
        '\t\t\t\t<file name = "xmasgf.arc" type = "data" source = "iso/gf/xmas.arc"/>\n'
        '\t\t\t\t<file name = "xmasp.arc" type = "data" source = "iso/xmasp/main.arc"/>\n'
        '\t\t\t\t<file name = "monsterx.arc" type = "data" source = "iso/monsterx/main.arc"/>\n',
        "Week 5 character disc assets",
    )
    once(
        xml,
        '\t\t\t\t<file name = "senpai.arc" type = "data" source = "iso/senpai/main.arc"/>\n',
        '\t\t\t\t<file name = "senpai.arc" type = "data" source = "iso/senpai/main.arc"/>\n'
        '\t\t\t\t<file name = "gfweeb.arc" type = "data" source = "iso/gf/weeb.arc"/>\n'
        '\t\t\t\t<file name = "senpaim.arc" type = "data" source = "iso/senpaim/main.arc"/>\n'
        '\t\t\t\t<file name = "spirit.arc" type = "data" source = "iso/spirit/main.arc"/>\n',
        "Week 6 character disc assets",
    )

    joined = "\n".join(path.read_text().lower() for path in (
        stage_c, root / "src/stagedef_disc1.h", makefile, xml,
    ))
    for marker in (
        "char_monster_new", "char_xmasbf_new", "char_xmasp_new", "char_monsterx_new",
        "back_week5evil_new", "char_gfweeb_new", "char_senpaim_new", "char_spirit_new",
        "back_week6_new", "monster.arc", "xmasp.arc", "back3.tim",
    ):
        if marker not in joined:
            raise SystemExit(f"base weeks v1 missing marker: {marker}")
    print("Applied authentic Week 2/5/6 stage and character restoration v1")


if __name__ == "__main__":
    main()
