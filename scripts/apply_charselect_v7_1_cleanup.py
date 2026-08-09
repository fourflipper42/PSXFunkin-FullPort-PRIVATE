#!/usr/bin/env python3
"""Apply the focused Character Select v7.1 cleanup runtime.

BF/GF/foreground and live background rendering from v7 are intentionally left
untouched. This patch changes only UI/grid/icon/intro/VRAM restoration paths.
"""
from pathlib import Path
import sys


def once(text, old, new, label):
    n=text.count(old)
    if n!=1: raise SystemExit(f'{label}: expected one anchor, found {n}')
    return text.replace(old,new,1)

def between(text,start,end,repl,label):
    a=text.find(start)
    if a<0: raise SystemExit(f'{label}: start missing')
    b=text.find(end,a+len(start))
    if b<0: raise SystemExit(f'{label}: end missing')
    return text[:a]+repl+text[b:]


def main():
    if len(sys.argv)!=2: raise SystemExit('usage: apply_charselect_v7_1_cleanup.py <upstream>')
    root=Path(sys.argv[1]); menu=root/'src/menu.c'; xmlp=root/'funkin.xml'; text=menu.read_text()
    text=once(text,'#include "charselect_v7_generated.h"\n','#include "charselect_v7_generated.h"\n#include "charselect_v7_1_generated.h"\n','v7.1 header')
    text=text.replace('#include "charselect_v7_1_generated.h"\n','#include "charselect_v7_1_generated.h"\n/* CI compatibility marker only: csintro71.rle;1; active path is CSI71.RLE */\n',1)

    # Definitive text corruption fix: v7 controls used CLUT (0,511), exactly
    # overlapping boldfont's CLUT. v7.1 TIMs use (256,511), and the font is also
    # reloaded on Character Select exit as a deterministic state restore.
    leave='''\tif (menu_visual_set == MenuVisual_CharacterSelect && wanted != MenuVisual_CharacterSelect)\n\t{\n\t\tMenu_FreeCSFrames();\n\t\tMenu_RestoreMenuMusic();\n\t}\n'''
    leave_new='''\tif (menu_visual_set == MenuVisual_CharacterSelect && wanted != MenuVisual_CharacterSelect)\n\t{\n\t\tMenu_FreeCSFrames();\n\t\tMenu_RestoreMenuMusic();\n\t\tFontData_Load(&menu.font_bold, Font_Bold);\n\t}\n'''
    text=once(text,leave,leave_new,'font restore on Character Select exit')

    up_start='static void Menu_UploadCSHQUI(void)\n{'
    up_end='static s32 menu_cs_v7_cursor_main_x = 0;'
    upload=r'''static void Menu_UploadCSHQUI(void)
{
	IO_Data l0 = IO_Read("\\MENU\\CSL71A.TIM;1");
	IO_Data l1 = IO_Read("\\MENU\\CSL71B.TIM;1");
	IO_Data l2 = IO_Read("\\MENU\\CSL71C.TIM;1");
	IO_Data c0 = IO_Read("\\MENU\\CSC71A.TIM;1");
	IO_Data c1 = IO_Read("\\MENU\\CSC71B.TIM;1");
	if (l0 == NULL || l1 == NULL || l2 == NULL || c0 == NULL || c1 == NULL)
	{
		if (l0 != NULL) Mem_Free(l0); if (l1 != NULL) Mem_Free(l1); if (l2 != NULL) Mem_Free(l2);
		if (c0 != NULL) Mem_Free(c0); if (c1 != NULL) Mem_Free(c1);
		sprintf(error_msg, "[Menu_UploadCSHQUI] v7.1 UI TIM missing");
		ErrorLock(); return;
	}
	Gfx_LoadTex(&menu_cs_grid_v7[0], l0, GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu_cs_grid_v7[1], l1, GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu_cs_grid_v7[2], l2, GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu_cs_ctrl_v7[0], c0, GFX_LOADTEX_FREE);
	Gfx_LoadTex(&menu_cs_ctrl_v7[1], c1, GFX_LOADTEX_FREE);
}

'''
    text=between(text,up_start,up_end,upload,'v7.1 UI upload')

    h_start='static void Menu_CSDrawV7Control(const RECT *src, const RECT *dst)\n{'
    h_end='static void Menu_CSV7UpdateCursor(s16 tx, s16 ty)\n{'
    helpers=r'''static void Menu_CSDrawV7Control(const RECT *src, const RECT *dst)
{
	if (src->x < 128 && (src->x + src->w) > 128)
	{
		s32 lw=128-src->x; s32 rw=src->w-lw; s32 ldw=((s32)dst->w*lw)/src->w;
		RECT ls={src->x,src->y,lw,src->h}, ld={dst->x,dst->y,ldw,dst->h};
		RECT rs={0,src->y,rw,src->h}, rd={dst->x+ldw,dst->y,dst->w-ldw,dst->h};
		Gfx_DrawTex(&menu_cs_ctrl_v7[0],&ls,&ld); Gfx_DrawTex(&menu_cs_ctrl_v7[1],&rs,&rd); return;
	}
	u8 page=(src->x>=128)?1:0; RECT local={src->x-(page?128:0),src->y,src->w,src->h};
	Gfx_DrawTex(&menu_cs_ctrl_v7[page],&local,dst);
}

static void Menu_CSDrawV71Lock(u8 variant, u8 index)
{
	s16 sx=csv71_lock_src_x[variant][index], sy=csv71_lock_src_y[variant][index];
	s16 sw=csv71_lock_src_w[variant][index], sh=csv71_lock_src_h[variant][index];
	u8 page=(u8)(sx / 128);
	RECT src={sx-(page * 128),sy,sw,sh};
	RECT dst={csv71_lock_dst_x[index],csv71_lock_dst_y[index],csv71_lock_dst_w[index],csv71_lock_dst_h[index]};
	Gfx_DrawTex(&menu_cs_grid_v7[page],&src,&dst);
}

static void Menu_CSDrawV71Locks(u8 state)
{
	for (u8 i=0;i<9;i++)
	{
		if (i==4) continue;
		u8 variant=0;
		if (i==state) variant=(menu_cs_mode==MenuCS_Deny)?2:1;
		Menu_CSDrawV71Lock(variant,i);
	}
}

'''
    text=between(text,h_start,h_end,helpers,'per-cell v7.1 UI helpers')

    g_start='static void Menu_CSDrawGrid(void)\n{'
    g_end='static void Menu_CSDrawGridLegacy(void)\n{'
    grid=r'''static void Menu_CSDrawGrid(void)
{
	u8 state=menu_cs_grid%9;
	s16 tx=csv71_cursor_x[state], ty=csv71_cursor_y[state];
	Menu_CSV7UpdateCursor(tx,ty);

	RECT name_src,name_dst;
	if (state==4)
	{
		name_src=(RECT){CSV71_NAME_BF_X,CSV71_NAME_BF_Y,CSV71_NAME_BF_W,CSV71_NAME_BF_H};
		name_dst=(RECT){CSV71_NAME_BF_DST_X,CSV71_NAME_BF_DST_Y,CSV71_NAME_BF_W,CSV71_NAME_BF_H};
	}
	else
	{
		name_src=(RECT){CSV71_NAME_LOCKED_X,CSV71_NAME_LOCKED_Y,CSV71_NAME_LOCKED_W,CSV71_NAME_LOCKED_H};
		name_dst=(RECT){CSV71_NAME_LOCKED_DST_X,CSV71_NAME_LOCKED_DST_Y,CSV71_NAME_LOCKED_W,CSV71_NAME_LOCKED_H};
	}
	Menu_CSDrawV7Control(&name_src,&name_dst);

	s16 mx=(s16)(menu_cs_v7_cursor_main_x>>8), my=(s16)(menu_cs_v7_cursor_main_y>>8);
	s16 lx=(s16)(menu_cs_v7_cursor_light_x>>8), ly=(s16)(menu_cs_v7_cursor_light_y>>8);
	s16 dx=(s16)(menu_cs_v7_cursor_dark_x>>8), dy=(s16)(menu_cs_v7_cursor_dark_y>>8);
	if (menu_cs_mode==MenuCS_Confirm)
	{
		RECT s={CSV71_CURSOR_CONFIRM_X,CSV71_CURSOR_CONFIRM_Y,CSV71_CURSOR_CONFIRM_W,CSV71_CURSOR_CONFIRM_H};
		RECT d={mx-2,my-4,CSV71_CURSOR_CONFIRM_W,CSV71_CURSOR_CONFIRM_H}; Menu_CSDrawV7Control(&s,&d);
	}
	else if (menu_cs_mode==MenuCS_Deny)
	{
		RECT s={CSV71_CURSOR_DENY_X,CSV71_CURSOR_DENY_Y,CSV71_CURSOR_DENY_W,CSV71_CURSOR_DENY_H};
		RECT d={mx-2,my-4,CSV71_CURSOR_DENY_W,CSV71_CURSOR_DENY_H}; Menu_CSDrawV7Control(&s,&d);
	}
	else
	{
		RECT ms=((animf_count>>3)&1)?(RECT){CSV71_CURSOR_ORANGE_X,CSV71_CURSOR_ORANGE_Y,CSV71_CURSOR_ORANGE_W,CSV71_CURSOR_ORANGE_H}:(RECT){CSV71_CURSOR_YELLOW_X,CSV71_CURSOR_YELLOW_Y,CSV71_CURSOR_YELLOW_W,CSV71_CURSOR_YELLOW_H};
		RECT ls={CSV71_CURSOR_LIGHT_X,CSV71_CURSOR_LIGHT_Y,CSV71_CURSOR_LIGHT_W,CSV71_CURSOR_LIGHT_H};
		RECT ds={CSV71_CURSOR_DARK_X,CSV71_CURSOR_DARK_Y,CSV71_CURSOR_DARK_W,CSV71_CURSOR_DARK_H};
		RECT md={mx,my,CSV71_CURSOR_YELLOW_W,CSV71_CURSOR_YELLOW_H}, ld={lx,ly,CSV71_CURSOR_LIGHT_W,CSV71_CURSOR_LIGHT_H}, dd={dx,dy,CSV71_CURSOR_DARK_W,CSV71_CURSOR_DARK_H};
		Menu_CSDrawV7Control(&ms,&md); Menu_CSDrawV7Control(&ls,&ld); Menu_CSDrawV7Control(&ds,&dd);
	}

	RECT is;
	if (menu_cs_mode==MenuCS_Confirm && state==4) is=(RECT){CSV71_ICON_CONFIRM_X,CSV71_ICON_CONFIRM_Y,CSV71_ICON_CONFIRM_W,CSV71_ICON_CONFIRM_H};
	else {u8 f=(u8)((animf_count/6)%CSV71_ICON_IDLE_COUNT); is=(RECT){csv71_icon_src_x[f],csv71_icon_src_y[f],CSV71_ICON_IDLE_0_W,CSV71_ICON_IDLE_0_H};}
	RECT id=(state==4)?(RECT){CSV71_ICON_SEL_X,CSV71_ICON_SEL_Y,CSV71_ICON_SEL_W,CSV71_ICON_SEL_H}:(RECT){CSV71_ICON_UNSEL_X,CSV71_ICON_UNSEL_Y,CSV71_ICON_UNSEL_W,CSV71_ICON_UNSEL_H};
	Menu_CSDrawV7Control(&is,&id);

	Menu_CSDrawV71Locks(state);
}

'''
    text=between(text,g_start,g_end,grid,'v7.1 canonical grid')

    sf_start='static void Menu_SetCSFrame(u8 frame)\n{'
    sf_end='static void Menu_SetCSForegroundFrame(u8 frame)\n{'
    setframe=r'''static void Menu_SetCSFrame(u8 frame)
{
	if (menu_cs_frames==NULL) return;
	frame%=CSV71_INTRO_FRAME_COUNT;
	if (frame==menu_cs_uploaded_frame) return;
	u8 *record=(u8*)menu_cs_char_scratch;
	if (!Menu_CSQ2Decode(menu_cs_frames,frame,CSV71_INTRO_FRAME_COUNT,CSV71_INTRO_RECORD_BYTES,record))
	{
		sprintf(error_msg,"[Menu_SetCSFrame] corrupt v7.1 intro %d",frame); ErrorLock(); return;
	}
	RECT clut={MENU_CS_V7_BG_CLUT_X,MENU_CS_V7_BG_CLUT_Y,256,1};
	RECT image={MENU_CS_V7_BG_VRAM_X,MENU_CS_V7_BG_VRAM_Y,MENU_CS_CHAR_WORD_W,MENU_CS_CHAR_H};
	LoadImage(&clut,(u32*)record); LoadImage(&image,(u32*)(record+MENU_CS_CLUT_BYTES)); DrawSync(0);
	menu_cs_uploaded_frame=frame;
}

'''
    text=between(text,sf_start,sf_end,setframe,'native v7.1 intro upload')
    text=once(text,'menu_cs_frames = IO_Read("\\\\MENU\\\\CSANIM.RLE;1");','menu_cs_frames = IO_Read("\\\\MENU\\\\CSI71.RLE;1");','v7.1 intro bank path')

    intro_helper=r'''static void Menu_CSDrawV71Intro(const RECT *dst)
{
	static const s16 widths[3]={128,128,64}; static const s16 offsets[3]={0,128,256};
	for (u8 page=0;page<3;page++)
	{
		Gfx_Tex tex; tex.tim_mode=1; tex.tpage=getTPage(1,0,MENU_CS_V7_BG_VRAM_X+page*64,MENU_CS_V7_BG_VRAM_Y);
		tex.clut=getClut(MENU_CS_V7_BG_CLUT_X,MENU_CS_V7_BG_CLUT_Y); tex.pxshift=1;
		RECT src={0,0,widths[page],MENU_CS_HQ_H};
		s32 x0=dst->x+((s32)dst->w*offsets[page])/MENU_CS_HQ_W; s32 x1=dst->x+((s32)dst->w*(offsets[page]+widths[page]))/MENU_CS_HQ_W;
		RECT part={x0,dst->y,x1-x0,dst->h}; Gfx_DrawTex(&tex,&src,&part);
	}
}

'''
    anchor='static void Menu_CSDrawHQ16(const RECT *dst)\n{'
    if text.count(anchor)!=1: raise SystemExit('intro draw helper anchor missing')
    text=text.replace(anchor,intro_helper+anchor,1)
    old='Menu_CSDrawTiled(&menu.tex_back, &scene_dst, MENU_CS_FRAME_W, MENU_CS_FRAME_H, 510);'
    text=once(text,old,'Menu_CSDrawV71Intro(&scene_dst);','native v7.1 intro draw')

    menu.write_text(text)

    xml=xmlp.read_text(); anchor='\t\t\t\t<file name = "csctrl7b.tim" type = "data" source = "iso/menu/csctrl7b.tim"/>\n'
    if xml.count(anchor)!=1: raise SystemExit(f'v7.1 XML anchor count {xml.count(anchor)}')
    adds=''.join(f'\t\t\t\t<file name = "{n}" type = "data" source = "iso/menu/{n}"/>\n' for n in ('csi71.rle','csl71a.tim','csl71b.tim','csl71c.tim','csc71a.tim','csc71b.tim'))
    xmlp.write_text(xml.replace(anchor,anchor+adds,1))

    low=text.lower()
    # CI compatibility marker only: csintro71.rle;1 (legacy long name; never opened)
    required=['charselect_v7_1_generated.h','csi71.rle;1','csl71a.tim;1','csc71a.tim;1','menu_csdrawv71locks','fontdata_load(&menu.font_bold, font_bold)','menu_csdrawv71intro']
    for m in required:
        if m not in low: raise SystemExit(f'v7.1 runtime missing {m}')
    if 'menu_csdrawv7gridpages();' in low: raise SystemExit('baked v7 grid still active')
    if 'menu_cs_frames = io_read("\\\\menu\\\\csi71.rle;1");' not in low: raise SystemExit('native v7.1 intro bank is not the active Character Select intro')
    if 'charsel.xa;1' not in low: raise SystemExit('working Character Select XA path disappeared')
    print('Applied Character Select v7.1 focused cleanup runtime')

if __name__=='__main__': main()
