#!/usr/bin/env python3
"""Build the initial BF Freeplay presentation, preserving complete DJ timelines."""
import argparse,json,sys
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image,ImageDraw,ImageFont,ImageChops
from build_menu_art import sparrow,tile_banks
from animateatlas_flatten import AnimateAtlas,render_leaves_fixed
from framebank import encode_images
from png_to_tim import encode_tim

def build(root,upstream,report_path):
    out=upstream/'iso/freeplay';out.mkdir(parents=True,exist_ok=True)
    records=[];arrays=[];files=[]
    def bank(name,frames,groups=None):
        data,record=encode_images(frames);(out/f'{name}.fbk').write_bytes(data)
        record.update(name=name,groups=groups or {},frame_rate=24)
        records.append(record);files.append(f'{name}.fbk')
        return record
    atlas=AnimateAtlas(root/'images/freeplay/freeplay-boyfriend')
    labels={l['name']:l for l in atlas.labels()}
    frames=[];groups={}
    for name in ('Intro','Idle','Confirm'):
        label=labels[name];groups[name]=[]
        for i in range(label['start'],label['start']+label['duration']):
            groups[name].append(len(frames))
            # Uniform 0.3 scale. Keep one stable screen-space canvas, including
            # the intentional lower-edge entrance, instead of recentering frames.
            frame=render_leaves_fixed(atlas.leaves_for_frame(i),(320,480),(.6,0,0,.6,396,180))
            frames.append(frame.resize((160,240),Image.Resampling.LANCZOS))
    bank('dj',frames,groups)
    for name,indices in groups.items():
        arrays.append('static const u16 freeplay_dj_'+name.lower()+'[] = {'+','.join(map(str,indices))+'};')
    frames,groups=sparrow(root/'images/freeplay/freeplayCapsule/capsule/freeplayCapsule.png',.23)
    bank('selected',[frames[i] for i in groups['mp3 capsule w backing']])
    bank('capsule',[frames[i] for i in groups['mp3 capsule w backing NOT SELECTED']])
    # Idle backing card's original tint and orange band, with an angled right
    # panel. Reflow the two panels to 4:3 without stretching either source image.
    bg=Image.new('RGBA',(320,240),(0,0,0,255))
    pink=Image.open(root/'images/freeplay/pinkBack.png').convert('RGBA')
    pink=pink.resize((round(pink.width*.3),round(pink.height*.3)),Image.Resampling.LANCZOS)
    pink=ImageChops.multiply(pink,Image.new('RGBA',pink.size,(255,216,99,255)))
    bg.alpha_composite(pink,(0,0));ImageDraw.Draw(bg).rectangle((0,132,160,154),fill=(254,218,0,255))
    right=Image.open(root/'images/freeplay/freeplayBGweek1-bf.png').convert('RGBA')
    scale=240/right.height;right=right.resize((round(right.width*scale),240),Image.Resampling.LANCZOS)
    panel=Image.new('RGBA',bg.size);panel.alpha_composite(right,(90,0))
    mask=Image.new('L',bg.size);ImageDraw.Draw(mask).polygon([(146,0),(320,0),(320,240),(102,240)],fill=255)
    bg=Image.composite(panel,bg,mask)
    ImageDraw.Draw(bg).rectangle((0,0,319,25),fill=(0,0,0,255))
    for i,(data,record) in enumerate(tile_banks([bg],160,240)):
        name=f'back{i}';(out/f'{name}.fbk').write_bytes(data);files.append(f'{name}.fbk')
        records.append(dict(record,name=name))
    diffs=[]
    for name in ('easy','normal','hard','erect','nightmare'):
        p=root/f'images/freeplay/freeplay{name}.png'
        if p.with_suffix('.xml').exists():
            images,groups=sparrow(p,.3)
        else:
            image=Image.open(p).convert('RGBA');images=[image.resize((round(image.width*.3),round(image.height*.3)),Image.Resampling.LANCZOS)]
        indices=[]
        for im in images:
            if im.width>96 or im.height>30:raise ValueError('Difficulty needs explicit layout adjustment')
            canvas=Image.new('RGBA',(96,30));canvas.alpha_composite(im,((96-im.width)//2,(30-im.height)//2))
            indices.append(len(diffs));diffs.append(canvas)
        arrays.append('static const u16 freeplay_diff_'+name+'[] = {'+','.join(map(str,indices))+'};')
    bank('diff',diffs)
    icon_names=('bf','dad','spooky','monster','pico','mom','parents-christmas','senpai','spirit','tankman','darnell','gf')
    icon_frames=[];icon_groups=[]
    for name in icon_names:
        images,groups=sparrow(root/f'images/freeplay/icons/{name}pixel.png',.5)
        base=len(icon_frames)
        icon_groups.append({k:[base+i for i in v] for k,v in groups.items()})
        for im in images:
            if im.width>40 or im.height>32:raise ValueError('Icon exceeds 40x32px cell')
            canvas=Image.new('RGBA',(40,32));canvas.alpha_composite(im,((40-im.width)//2,(32-im.height)//2));icon_frames.append(canvas)
    for page in range((len(icon_frames)+47)//48):
        canvas=Image.new('RGBA',(240,256))
        for i,im in enumerate(icon_frames[page*48:(page+1)*48]):canvas.alpha_composite(im,((i%6)*40,(i//6)*32))
        (out/f'icons{page}.tim').write_bytes(encode_tim(canvas,8,640+page*128,256,0,488+page));files.append(f'icons{page}.tim')
    arrays.append('static const u16 freeplay_icon_idle[] = {'+','.join(str(g['idle'][0]) for g in icon_groups)+'};')
    for i,g in enumerate(icon_groups):arrays.append('static const u16 freeplay_icon_confirm_'+str(i)+'[] = {'+','.join(map(str,g['confirm']))+'};')
    arrays.append('static const u16 *const freeplay_icon_confirm[] = {'+','.join('freeplay_icon_confirm_'+str(i) for i in range(len(icon_groups)))+'};')
    arrays.append('static const u16 freeplay_icon_counts[] = {'+','.join(str(len(g['confirm'])) for g in icon_groups)+'};')
    # Monochrome rasterization keeps this pixel font's half-pixel outlines
    # from splitting into two alpha<128 columns, which PS1 would discard.
    font=ImageFont.truetype(str(root/'fonts/5by7.ttf'),10)
    font_image=Image.new('RGBA',(128,84));draw=ImageDraw.Draw(font_image)
    draw.fontmode='1'
    for i in range(96):draw.text(((i%16)*8,(i//16)*14+11),chr(i+32),font=font,fill='white',anchor='ls')
    (out/'font.tim').write_bytes(encode_tim(font_image,4,896,256,0,500));files.append('font.tim')
    total=sum((out/name).stat().st_size for name in files)
    # Leave room for CD-sector padding, allocator headers and resident SFX load.
    if total>850000:raise ValueError(f'Freeplay bank uses {total} bytes; exceeds the page budget')
    header='#ifndef FREEPLAY_ART_GENERATED_H\n#define FREEPLAY_ART_GENERATED_H\n'+'\n'.join(arrays)+'\n#endif\n'
    (upstream/'src/freeplay_art_generated.h').write_text(header)
    xml=ET.parse(upstream/'funkin.xml');parent=xml.find(".//dir[@name='menu']/..")
    if parent is None:raise ValueError('Cannot locate disc root')
    directory=parent.find("dir[@name='freeplay']")
    if directory is None:directory=ET.SubElement(parent,'dir',name='freeplay')
    for filename in files:
        if directory.find(f"file[@name='{filename}']") is None:ET.SubElement(directory,'file',name=filename,type='data',source=f'iso/freeplay/{filename}')
    xml.write(upstream/'funkin.xml',encoding='utf-8',xml_declaration=True)
    report=dict(viewport=[320,240],banks=records,asset_bytes=total,asset_budget_bytes=850000,
                icon_names=icon_names,icon_groups=icon_groups,icon_frames=len(icon_frames),
                implemented_dj_animations=['Intro','Idle','Confirm'],remaining_dj_animations=[k for k in labels if k not in ('Intro','Idle','Confirm')])
    report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(asset_bytes=total,dj_frames=records[0]['frames'],banks=len(records))))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','upstream','report'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();build(a.root,a.upstream,a.report)
