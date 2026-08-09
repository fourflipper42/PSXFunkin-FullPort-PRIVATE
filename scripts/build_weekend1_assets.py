#!/usr/bin/env python3
"""Generate native PSXFunkin Weekend 1 character/background assets and C modules.

Only official v0.8.4 artwork is used. Animate atlases are flattened into a small
set of authentic source frames suitable for the PS1 renderer; no AI/generated
art or tween interpolation is used.
"""
from __future__ import annotations
import argparse, json, math, shutil, sys, xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image, ImageColor

HERE=Path(__file__).resolve().parent
PS1=HERE/'ps1asset'
sys.path.insert(0,str(PS1))
from build_character_pages import build as build_pages
from png_to_tim import encode_tim, decode_tim
from arc_pack import pack_arc

VRAM={
 'pico':(448,0,0,480), 'nene':(512,0,16,480), 'darnell':(576,0,32,480),
 'picobl':(448,0,0,480), 'darnbl':(576,0,32,480),
}

def c_ident(s:str)->str: return ''.join(ch if ch.isalnum() else '_' for ch in s)
def animation_script(frames:list[int], loop=True, change:int|None=None)->str:
    if not frames: frames=[0]
    vals=', '.join(str(i) for i in frames)
    if change is not None: return '{'+vals+', ASCR_CHGANI, '+str(change)+'}'
    if loop: return '{'+vals+', ASCR_BACK, '+str(max(1,len(frames)))+'}'
    return '{'+vals+', ASCR_REPEAT}'

def merge_components(data_root:Path, out:Path, name:str, components:list[tuple[str,str]], vram_key:str):
    vx,vy,cx,cy=VRAM[vram_key]; all_frames=[]; all_pages=[]; label_map={}; page_offset=0; frame_offset=0
    for sub,prefix in components:
        comp=out/f'_component_{prefix}'
        m=build_pages(data_root/'shared/images/characters'/sub, comp, prefix, 4, vx,vy,cx,cy,'all')
        for p in m['pages']:
            src=comp/p['tim']; member=f'{prefix}{p["index"]:02d}.tim'; dst=out/member; shutil.copyfile(src,dst); all_pages.append({'member':member,'path':str(dst)})
        for f in m['frames']:
            nf=dict(f); nf['index']=frame_offset+f['index']; nf['page']=page_offset+f['page']; nf['label']=f'{prefix}:{f["label"]}'
            all_frames.append(nf); label_map.setdefault(nf['label'],[]).append(nf['index'])
        page_offset+=len(m['pages']); frame_offset+=len(m['frames'])
    if page_offset>16: raise ValueError(f'{name}: {page_offset} pages exceeds ARC/runtime max 16')
    pack_arc(out/'main.arc',[Path(p['path']) for p in all_pages],[p['member'] for p in all_pages])
    merged={'name':name,'pages':all_pages,'frames':all_frames,'label_map':label_map,'vram':[vx,vy,cx,cy]}
    (out/'manifest.json').write_text(json.dumps(merged,indent=2)); return merged

def lbl(m,prefix,label): return m['label_map'].get(f'{prefix}:{label}',[])
def add_anim(lines,name,frames,spd=2,loop=True,change=None):
    lines.append(f'static const u8 {name}_scr[] = {animation_script(frames,loop,change)};'); return f'{{{spd}, {name}_scr}}'
def make_standard_anim_entries(lines,base,mapping):
    entries=[]
    for key in ['idle','left','left_alt','down','down_alt','up','up_alt','right','right_alt']:
        frames=mapping.get(key) or mapping.get(key.replace('_alt','')) or mapping['idle']; entries.append(add_anim(lines,f'{base}_{key}',frames,2,True))
    return entries

def write_char_module(srcdir:Path, ctor:str, arcpath:str, m:dict, role:str, mapping:dict, custom:list[tuple[str,list[int],bool,int|None]], health:int, focus:tuple[int,int,int]):
    stem=ctor.replace('Char_','').replace('_New','').lower(); hname=f'{stem}.h'; cname=f'{stem}.c'; enum_names=[]
    lines=['#include "'+hname+'"','#include "../mem.h"','#include "../archive.h"','#include "../stage.h"','#include "../main.h"','',
           'typedef struct {','    Character character;','    IO_Data arc_main;','    IO_Data arc_ptr[16];','    Gfx_Tex tex;','    u8 frame, tex_id;','} ModernGenerated;','']
    lines.append('static const CharFrame frames[] = {')
    for f in m['frames']:
        x,y,w,h=f['src']; ox,oy=f['offset']; lines.append(f'    {{{f["page"]}, {{{x},{y},{w},{h}}}, {{{ox},{oy}}}}},')
    lines.append('};\n'); anim_defs=[]; entries=make_standard_anim_entries(anim_defs,stem,mapping)
    if role=='player':
        entries.append(add_anim(anim_defs,f'{stem}_peace',mapping['idle'],2,True)); entries.append(add_anim(anim_defs,f'{stem}_sweat',mapping['idle'],2,True))
        death_intro=mapping.get('death_intro',mapping['idle']); death_loop=mapping.get('death_loop',mapping['idle']); death_confirm=mapping.get('death_confirm',death_loop)
        entries.append(add_anim(anim_defs,f'{stem}_dead0',death_intro,2,False,12)); entries.append(add_anim(anim_defs,f'{stem}_dead1',death_loop,2,True))
        entries.append(add_anim(anim_defs,f'{stem}_dead2',death_loop,2,False,14)); entries.append(add_anim(anim_defs,f'{stem}_dead3',death_loop,2,True))
        entries.append(add_anim(anim_defs,f'{stem}_dead4',death_loop,2,False,14)); entries.append(add_anim(anim_defs,f'{stem}_dead5',death_loop,2,False,14))
        entries.append(add_anim(anim_defs,f'{stem}_dead6',death_confirm,2,False,18)); entries.append(add_anim(anim_defs,f'{stem}_dead7',death_confirm,2,True))
    start_custom=19 if role=='player' else 9
    for i,(nm,fr,loop,chg) in enumerate(custom):
        enum_names.append((nm,start_custom+i)); entries.append(add_anim(anim_defs,f'{stem}_{c_ident(nm).lower()}',fr,2,loop,chg))
    lines += anim_defs; lines.append('static const Animation anims[] = {'); lines += [f'    {e},' for e in entries]; lines.append('};\n')
    lines.append('static const char *const page_names[] = {'); lines += [f'    "{p["member"]}",' for p in m['pages']]; lines.append('    NULL\n};\n')
    lines += [
    'static void SetFrame(void *user, u8 frame) {','    ModernGenerated *this=(ModernGenerated*)user;','    if (frame != this->frame) {','        const CharFrame *cf=&frames[this->frame=frame];','        if (cf->tex != this->tex_id) Gfx_LoadTex(&this->tex, this->arc_ptr[this->tex_id=cf->tex], 0);','    }','}',
    'static void Tick(Character *character) {','    ModernGenerated *this=(ModernGenerated*)character;','    Character_CheckEndSing(character);','    if ((stage.flag & STAGE_FLAG_JUST_STEP) && Animatable_Ended(&character->animatable) && (stage.song_step & 0x7)==0)','        character->set_anim(character, CharAnim_Idle);','    Animatable_Animate(&character->animatable,(void*)this,SetFrame);','    Character_Draw(character,&this->tex,&frames[this->frame]);','}',
    'static void SetAnim(Character *character,u8 anim) { Animatable_SetAnim(&character->animatable,anim); Character_CheckStartSing(character); }',
    'static void Free(Character *character) { ModernGenerated *this=(ModernGenerated*)character; Mem_Free(this->arc_main); }',
    f'Character *{ctor}(fixed_t x, fixed_t y) {{','    ModernGenerated *this=Mem_Alloc(sizeof(ModernGenerated));',f'    if (!this) {{ sprintf(error_msg,"[{ctor}] allocation failed"); ErrorLock(); return NULL; }}','    this->character.tick=Tick; this->character.set_anim=SetAnim; this->character.free=Free;','    Animatable_Init(&this->character.animatable,anims); Character_Init((Character*)this,x,y);',f'    this->character.health_i={health};',f'    this->character.focus_x=FIXED_DEC({focus[0]},1); this->character.focus_y=FIXED_DEC({focus[1]},1); this->character.focus_zoom=FIXED_DEC({focus[2]},100);',f'    this->arc_main=IO_Read("{arcpath}");','    const char *const *pp=page_names; IO_Data *ap=this->arc_ptr; for (; *pp; ++pp) *ap++=Archive_Find(this->arc_main,*pp);','    this->tex_id=this->frame=0xFF;','    return (Character*)this;','}','']
    srcdir.mkdir(parents=True,exist_ok=True); (srcdir/cname).write_text('\n'.join(lines))
    hl=['#ifndef _'+c_ident(stem).upper()+'_H','#define _'+c_ident(stem).upper()+'_H','#include "../character.h"']
    if role=='player': hl.append('#include "../player.h"')
    if enum_names:
        hl.append('enum {'); hl += [f'    {ctor.replace("Char_","").replace("_New","")}_{c_ident(nm)} = {val},' for nm,val in enum_names]; hl.append('};')
    hl += [f'Character *{ctor}(fixed_t x, fixed_t y);','#endif','']; (srcdir/hname).write_text('\n'.join(hl)); return cname,hname,enum_names

def crop_sparrow(image:Image.Image, xml_path:Path, prefix:str|None):
    root=ET.parse(xml_path).getroot(); nodes=root.findall('.//SubTexture')
    if prefix:
        cand=[n for n in nodes if n.attrib.get('name','').startswith(prefix)]
        if cand: nodes=cand
    if not nodes: return image
    a=nodes[0].attrib; x,y,w,h=[int(float(a[k])) for k in ('x','y','width','height')]; crop=image.crop((x,y,x+w,y+h))
    fw=int(float(a.get('frameWidth',w))); fh=int(float(a.get('frameHeight',h))); fx=int(float(a.get('frameX',0))); fy=int(float(a.get('frameY',0)))
    if fw!=w or fh!=h or fx or fy:
        can=Image.new('RGBA',(fw,fh)); can.alpha_composite(crop,(-fx,-fy)); crop=can
    return crop

def sparrow_sequence(base:Path, prefix:str)->list[Image.Image]:
    """Return authentic Sparrow frames on their declared untrimmed canvases."""
    sheet=Image.open(base.with_suffix('.png')).convert('RGBA')
    nodes=[n for n in ET.parse(base.with_suffix('.xml')).getroot().findall('.//SubTexture')
           if n.attrib.get('name','').startswith(prefix)]
    nodes.sort(key=lambda n:n.attrib.get('name',''))
    frames=[]
    for node in nodes:
        a=node.attrib; x,y,w,h=[int(float(a[k])) for k in ('x','y','width','height')]
        crop=sheet.crop((x,y,x+w,y+h))
        fw=int(float(a.get('frameWidth',w))); fh=int(float(a.get('frameHeight',h)))
        fx=int(float(a.get('frameX',0))); fy=int(float(a.get('frameY',0)))
        frame=Image.new('RGBA',(fw,fh)); frame.alpha_composite(crop,(-fx,-fy)); frames.append(frame)
    if not frames: raise ValueError(f'{base}: no Sparrow frames for {prefix}')
    return frames

def sample_indices(length:int,count:int)->list[int]:
    if length<=count: return list(range(length))
    return sorted({round(i*(length-1)/(count-1)) for i in range(count)})

def stage_fx_cell(image:Image.Image, scale:float)->Image.Image:
    nw=max(1,round(image.width*scale)); nh=max(1,round(image.height*scale))
    if nw>124 or nh>124:
        fit=min(124/image.width,124/image.height); nw=max(1,round(image.width*fit)); nh=max(1,round(image.height*fit))
    image=image.resize((nw,nh),Image.Resampling.LANCZOS)
    cell=Image.new('RGBA',(128,128)); cell.alpha_composite(image,((128-nw)//2,128-nh)); return cell

def pack_stage_fx(cells:list[tuple[str,Image.Image]],out:Path,arc_name:str,vram_x:int,clut_x:int)->dict:
    """Pack fixed 128px cells into stage-local four-page TIM archives."""
    out.mkdir(parents=True,exist_ok=True); pages=[]; frames={}
    for index,(label,cell) in enumerate(cells):
        page=index//4; slot=index%4; frames.setdefault(label,[]).append({
            'tex':page,'src':[(slot%2)*128,(slot//2)*128,128,128]
        })
    for page_index in range(math.ceil(len(cells)/4)):
        page=Image.new('RGBA',(256,256))
        for slot in range(4):
            index=page_index*4+slot
            if index>=len(cells): break
            page.alpha_composite(cells[index][1],((slot%2)*128,(slot//2)*128))
        tim=encode_tim(page,4,vram_x+page_index*64,0,clut_x+page_index*16,480)
        path=out/f'fx{page_index:02d}.tim'; path.write_bytes(tim); assert decode_tim(tim).size==(256,256); pages.append(path)
    if len(pages)>4: raise ValueError(f'{arc_name}: {len(pages)} pages exceeds stage VRAM budget')
    pack_arc(out/arc_name,pages,[p.name for p in pages]); return {'pages':len(pages),'frames':frames}

def write_fx_header(path:Path,street:dict,blazin:dict)->None:
    lines=['#ifndef _WEEKEND1_FX_GENERATED_H','#define _WEEKEND1_FX_GENERATED_H','']
    for key,rows in [('street_car',street['frames']['car']),('street_green',street['frames']['green']),
                     ('street_red',street['frames']['red']),('blazin_lightning',blazin['frames']['lightning'])]:
        lines.append(f'static const Weekend1SpriteFrame w1_{key}[] = {{')
        for row in rows:
            x,y,w,h=row['src']; lines.append(f'    {{{row["tex"]}, {{{x},{y},{w},{h}}}}},')
        lines.append('};'); lines.append(f'#define W1_{key.upper()}_COUNT {len(rows)}'); lines.append('')
    lines.append('#endif'); path.write_text('\n'.join(lines)+'\n')

def build_stage_fx(data_root:Path,upstream:Path,builddir:Path)->dict:
    street_base=data_root/'weekend1/images/phillyStreets'
    car_frames=sparrow_sequence(street_base/'phillyCars','car')
    green=sparrow_sequence(street_base/'phillyTraffic','redtogreen')
    red=sparrow_sequence(street_base/'phillyTraffic','greentored')
    street_cells=[]
    street_cells += [('car',stage_fx_cell(frame,0.22)) for frame in car_frames]
    street_cells += [('green',stage_fx_cell(green[i],0.22)) for i in sample_indices(len(green),4)]
    street_cells += [('red',stage_fx_cell(red[i],0.22)) for i in sample_indices(len(red),4)]
    street=pack_stage_fx(street_cells,builddir/'streetfx','streetfx.arc',768,80)

    lightning=sparrow_sequence(data_root/'weekend1/images/phillyBlazin/lightning','lightning')
    lightning_cells=[('lightning',stage_fx_cell(lightning[i],0.34)) for i in sample_indices(len(lightning),16)]
    blazin=pack_stage_fx(lightning_cells,builddir/'blazinfx','blazinfx.arc',768,80)
    shutil.copyfile(builddir/'streetfx/streetfx.arc',upstream/'iso/week8/streetfx.arc')
    shutil.copyfile(builddir/'blazinfx/blazinfx.arc',upstream/'iso/week8/blazinfx.arc')
    write_fx_header(upstream/'src/weekend1_fx_generated.h',street,blazin)
    return {'street':street,'blazin':blazin}

def compose_stage(data_root:Path, stage_name:str, images_subdir:str, out:Path, xref:float, yref:float, scale:float, vram_xs=(640,704), clut_xs=(48,64)):
    st=json.loads((data_root/'data/stages'/f'{stage_name}.json').read_text()); canvas=Image.new('RGBA',(512,240),(0,0,0,255)); props=sorted(st.get('props',[]),key=lambda p:p.get('zIndex',0))
    for p in props:
        if p.get('zIndex',0) >= 300: continue
        ap=p.get('assetPath','')
        if ap.startswith('#'):
            if p.get('zIndex',0) == 0: canvas.alpha_composite(Image.new('RGBA',(512,240),ImageColor.getcolor(ap,'RGBA')))
            continue
        imgpath=data_root/images_subdir/(ap+'.png')
        if not imgpath.exists(): continue
        try: im=Image.open(imgpath).convert('RGBA')
        except Exception: continue
        xml=imgpath.with_suffix('.xml'); anims=p.get('animations') or []
        # Animated traffic, cars, and lightning are emitted separately below.
        if xml.exists() and anims: continue
        sx,sy=p.get('scale',[1,1]); sx*=scale; sy*=scale; nw=max(1,round(im.width*abs(sx))); nh=max(1,round(im.height*abs(sy)))
        if nw>4096 or nh>4096: continue
        im=im.resize((nw,nh),Image.Resampling.LANCZOS)
        if p.get('flipX'): im=im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if p.get('flipY'): im=im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        if p.get('angle'): im=im.rotate(-float(p['angle']),expand=True,resample=Image.Resampling.BICUBIC)
        alpha=float(p.get('alpha',1))
        if alpha<1: im.putalpha(im.getchannel('A').point(lambda v:int(v*alpha)))
        px,py=p.get('position',[0,0]); x=round(256+(px-xref)*scale); y=round(120+(py-yref)*scale); canvas.alpha_composite(im,(x,y))
    out.mkdir(parents=True,exist_ok=True); canvas.save(out/f'{stage_name}_preview.png'); pages=[]
    for i in range(2):
        page=canvas.crop((i*256,0,(i+1)*256,240)); tim=encode_tim(page,4,vram_xs[i],0,clut_xs[i],480); p=out/f'back{i}.tim'; p.write_bytes(tim); assert decode_tim(tim).size==(256,240); pages.append(p)
    pack_arc(out/'back.arc',pages,['back0.tim','back1.tim'])

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); ap.add_argument('--upstream',type=Path,required=True); ap.add_argument('--report',type=Path,required=True); a=ap.parse_args(); root=a.root; up=a.upstream; builddir=up/'build-weekend1'; shutil.rmtree(builddir,ignore_errors=True); builddir.mkdir(parents=True); charsrc=up/'src/character'; records=[]
    p=merge_components(root,builddir/'pico','picoplay',[('pico/basic-animations','pb'),('pico/playable-animations','px'),('pico/death','pd')],'pico')
    mp={'idle':lbl(p,'pb','Idle'),'left':lbl(p,'pb','Left'),'down':lbl(p,'pb','Down'),'up':lbl(p,'pb','Up'),'right':lbl(p,'pb','Right'),'death_intro':lbl(p,'pd','Death Intro'),'death_loop':lbl(p,'pd','Death Loop'),'death_confirm':lbl(p,'pd','Death Confirm')}
    custom=[
      ('Miss_Left',lbl(p,'px','Left Miss'),False,0),('Miss_Down',lbl(p,'px','Down Miss'),False,0),
      ('Miss_Up',lbl(p,'px','Up Miss'),False,0),('Miss_Right',lbl(p,'px','Right Miss'),False,0),
      ('Hey',lbl(p,'px','Hey'),False,0),('Cheer',lbl(p,'px','Cheer'),False,0),
      ('BurpShit',lbl(p,'px','*BURP* ... Shit'),False,0),('BurpSmile',lbl(p,'px','Burp Smile'),False,0),
      ('BurpCensor',lbl(p,'px','Burp Censor'),False,0),
      ('Shoot',lbl(p,'px','Shoot'),False,0),('ShootReturn',lbl(p,'px','Shoot and Return'),False,0),
      ('GunReload',lbl(p,'px','Gun Reload'),False,0),('Hit',lbl(p,'px','Hit'),False,0),
      ('PissedOff',lbl(p,'px','Pissed Off'),False,0),
    ]
    write_char_module(charsrc,'Char_PicoPlayer_New','\\\\CHAR\\\\PICOPLAY.ARC;1',p,'player',mp,custom,3,(-50,-65,100)); shutil.copyfile(builddir/'pico/main.arc',up/'iso'/'picoplay.arc')
    n=merge_components(root,builddir/'nene','nene',[('nene','ne')],'nene'); idle=lbl(n,'ne','Idle'); fawn=lbl(n,'ne','Fawn'); mn={'idle':idle,'left':idle,'down':fawn or idle,'up':idle,'right':idle}; custom=[('KnifeRaise',lbl(n,'ne','Knife Raise'),False,0),('KnifeIdle',lbl(n,'ne','Idle (holding Knife)'),True,None),('KnifeLower',lbl(n,'ne','Knife Lower'),False,0),('Laugh',lbl(n,'ne','Laugh'),False,0),('Cheer',lbl(n,'ne','Cheer'),False,0),('HairBlow',lbl(n,'ne','Hair Blow'),True,None)]
    write_char_module(charsrc,'Char_Nene_New','\\\\CHAR\\\\NENE.ARC;1',n,'character',mn,custom,4,(0,-50,100)); shutil.copyfile(builddir/'nene/main.arc',up/'iso'/'nene.arc')
    d=merge_components(root,builddir/'darnell','darnell',[('darnell','da')],'darnell')
    def dl(direction): return lbl(d,'da',f'Pose {direction}')+lbl(d,'da',f'{direction} Flame Loop')
    md={'idle':lbl(d,'da','Idle'),'left':dl('Left'),'down':dl('Down'),'up':dl('Up'),'right':dl('Right')}; custom=[('LightCan',lbl(d,'da','Light Can'),False,0),('KickUp',lbl(d,'da','Kick Up'),False,0),('KneeForward',lbl(d,'da','Knee Forward'),False,0),('Pissed',lbl(d,'da','Gets Pissed'),False,0),('Laugh',lbl(d,'da','Laugh'),False,0)]
    write_char_module(charsrc,'Char_Darnell_New','\\\\CHAR\\\\DARNELL.ARC;1',d,'character',md,custom,5,(50,-70,100)); shutil.copyfile(builddir/'darnell/main.arc',up/'iso'/'darnell.arc')
    pb=merge_components(root,builddir/'picobl','picobl',[('picoBlazin','pi')],'picobl'); idle=lbl(pb,'pi','Idle'); mb={'idle':idle,'left':lbl(pb,'pi','Punch High 1'),'down':lbl(pb,'pi','Punch Low 1'),'up':lbl(pb,'pi','Dodge'),'right':lbl(pb,'pi','Punch High 2'),'death_intro':lbl(pb,'pi','Low Death Intro'),'death_loop':lbl(pb,'pi','Low Death Loop'),'death_confirm':lbl(pb,'pi','Low Death Confirm')}; pcb_names=['Block','Dodge','Punch High 1','Punch High 2','Punch Low 1','Punch Low 2','Hit Low','Hit High','Uppercut Hit','Fake Hit','Taunt','Taunt Laugh Loop','Uppercut Prep','Uppercut Punch','Uppercut Punch Loop','Hit Spin']; custom=[(x,lbl(pb,'pi',x),('Loop' in x),(None if 'Loop' in x else 0)) for x in pcb_names]
    write_char_module(charsrc,'Char_PicoBlazin_New','\\\\CHAR\\\\PICOBL.ARC;1',pb,'player',mb,custom,3,(-30,-55,100)); shutil.copyfile(builddir/'picobl/main.arc',up/'iso'/'picobl.arc')
    db=merge_components(root,builddir/'darnbl','darnbl',[('darnellBlazin','db')],'darnbl'); idle=lbl(db,'db','Idle'); mdb={'idle':idle,'left':lbl(db,'db','Punch High 1'),'down':lbl(db,'db','Punch Low 1'),'up':lbl(db,'db','Dodge'),'right':lbl(db,'db','Punch High 2')}; db_names=['Uppercut Prep','Uppercut Punch','Uppercut Punch Loop','Fake Hit','Block','Punch High 1','Punch High 2','Punch Low 1','Punch Low 2','Dodge','Hit High','Hit Low','Cringe','Hit Spin','Pissed','Uppercut Hit']; custom=[(x,lbl(db,'db',x),('Loop' in x),(None if 'Loop' in x else 0)) for x in db_names]
    write_char_module(charsrc,'Char_DarnellBlazin_New','\\\\CHAR\\\\DARNBL.ARC;1',db,'character',mdb,custom,5,(30,-55,100)); shutil.copyfile(builddir/'darnbl/main.arc',up/'iso'/'darnbl.arc')
    w8=up/'iso/week8'; compose_stage(root,'phillyStreets','weekend1/images',w8,1453,1150,0.22); compose_stage(root,'phillyBlazin','weekend1/images',builddir/'blazinbg',-237,150,0.22); shutil.copyfile(builddir/'blazinbg/back.arc',w8/'blazin.arc')
    fx=build_stage_fx(root,up,builddir)
    for nm,m in [('pico',p),('nene',n),('darnell',d),('picobl',pb),('darnbl',db)]: records.append({'name':nm,'frames':len(m['frames']),'pages':len(m['pages'])})
    payload={'characters':records,'stage_fx':fx,'policy':'authentic-v0.8.4-source-frames-only'}
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(payload,indent=2)+'\n'); print(json.dumps(payload,indent=2))
if __name__=='__main__': main()
