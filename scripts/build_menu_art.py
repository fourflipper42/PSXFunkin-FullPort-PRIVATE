#!/usr/bin/env python3
"""Build official animated menu art for a 320x240 PS1 viewport; retain every frame."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import re
import sys
import textwrap
import unicodedata
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, str(Path(__file__).resolve().parent/'ps1asset'))
from framebank import encode_images, unpack_indices, pack_indices
from png_to_tim import encode_tim

MAIN = ['storymode','freeplay','merch','options','credits']

def sparrow(path: Path, scale: float):
    sheet = Image.open(path).convert('RGBA')
    nodes = ET.parse(path.with_suffix('.xml')).getroot().findall('SubTexture')
    if not nodes: raise ValueError(f'No frames in {path}')
    def number(n,k,default=None): return int(float(n.attrib.get(k, default)))
    sizes = [(number(n,'frameWidth',n.attrib['width']), number(n,'frameHeight',n.attrib['height'])) for n in nodes]
    width = (math.ceil(max(w for w,h in sizes)*scale)+1)&~1
    height = math.ceil(max(h for w,h in sizes)*scale)
    if width>256 or height>256: raise ValueError(f'{path} needs tiles at scale {scale}: {width}x{height}')
    frames=[]; groups={}
    for n,(fw,fh) in zip(nodes,sizes):
        x,y,w,h=[number(n,k) for k in ('x','y','width','height')]
        crop=sheet.crop((x,y,x+w,y+h))
        if n.attrib.get('rotated','false').lower()=='true': crop=crop.transpose(Image.Transpose.ROTATE_90)
        # Restore trimming before centering; retain each animation's intended
        # center and scale instead of stretching differently-sized frames.
        canvas=Image.new('RGBA',(fw,fh))
        canvas.alpha_composite(crop,(-number(n,'frameX',0),-number(n,'frameY',0)))
        target=Image.new('RGBA',(width,height))
        scaled=canvas.resize((max(1,round(fw*scale)),max(1,round(fh*scale))),Image.Resampling.LANCZOS)
        target.alpha_composite(scaled,((width-scaled.width)//2,(height-scaled.height)//2))
        frames.append(target)
        group=re.sub(r'\d+$','',n.attrib['name']).strip()
        groups.setdefault(group,[]).append((n.attrib['name'],len(frames)-1))
    groups={key:[idx for name,idx in sorted(entries)] for key,entries in groups.items()}
    return frames,groups

def ctext(text):
    text=unicodedata.normalize('NFKD',text).encode('ascii','replace').decode()
    return json.dumps(text)

def build(root: Path, upstream: Path, report_path: Path):
    out=upstream/'iso/menu';out.mkdir(parents=True,exist_ok=True)
    reports=[];definitions=[];arraydefs=[]
    specs=[(name,f'mainmenu/{name}.png',0.25) for name in MAIN]+[('logo','logoBumpin.png',0.18),('titlegf','gfDanceTitle.png',0.18)]
    for index,(name,source,scale) in enumerate(specs):
        frames,groups=sparrow(root/'images'/source,scale)
        data,record=encode_images(frames)
        disk_name = 'story' if name == 'storymode' else name
        (out/f'{disk_name}.fbk').write_bytes(data)
        record.update(name=name,source=source,scale=scale,groups=groups,frame_rate=24)
        reports.append(record)
        if index<5:
            idle=groups[f'{name} idle'];selected=groups[f'{name} selected']
        else:
            idle=next(iter(groups.values()));selected=idle
        for suffix,values in [('idle',idle),('selected',selected)]:
            arraydefs.append(f'static const u16 menu_{name}_{suffix}[] = {{'+','.join(map(str,values))+'};')
        x=[384,512,640,768,768,384,640][index]
        y=[0,0,0,0,256,0,0][index]
        definitions.append(f'{{"\\\\MENU\\\\{disk_name.upper()}.FBK;1", {x}, {y}, {482+index}, menu_{name}_idle, {len(idle)}, menu_{name}_selected, {len(selected)}}}')
    # Center crop decorative background to 4:3; do not distort its proportions.
    bg=Image.open(root/'images/menuBG.png').convert('RGBA')
    crop_width=round(bg.height*4/3)
    bg=bg.crop(((bg.width-crop_width)//2,0,(bg.width+crop_width)//2,bg.height)).resize((320,240),Image.Resampling.LANCZOS)
    data,record=encode_images([bg.crop((0,0,160,240)),bg.crop((160,0,320,240))])
    _,_,palette,indexed=unpack_indices(data)
    for i,frame in enumerate(indexed):
        (out/f'back{i}.fbk').write_bytes(pack_indices(160,240,palette,[frame]))
    reports.append(dict(record,name='background',frames_dropped=0))
    # Compact text for lists/status/credits from the official VCR face.
    font=ImageFont.truetype(str(root/'fonts/vcr.ttf'),10)
    atlas=Image.new('RGBA',(128,72));draw=ImageDraw.Draw(atlas)
    for i in range(96):
        draw.text(((i%16)*8,(i//16)*12+9),chr(i+32),font=font,fill='white',anchor='ls')
    (out/'small.tim').write_bytes(encode_tim(atlas,4,896,256,0,500))
    header='#ifndef MENU_ART_GENERATED_H\n#define MENU_ART_GENERATED_H\n'+'\n'.join(arraydefs)+'\nstatic const MenuArtDef menu_art_defs[] = {\n'+',\n'.join(definitions)+'\n};\n'
    credits=json.loads((root/'exclude/data/credits.json').read_text())
    lines=[]
    for entry in credits['entries']:
        if entry.get('header'):lines.extend(['']+textwrap.wrap(entry['header'],36))
        for person in entry.get('body',[]):
            lines.extend(textwrap.wrap(person['line'],36) or [''])
        # v0.8.4 fetchBackerEntries() returns []; retain the shipped credits.
    # Retain original project attribution as well as the official game's credits.
    lines.extend(['','PLAYSTATION PORT','CUCKYDEV / PSXFUNKIN','','FULL PORT','FOURFLIPPER42'])
    header+='static const char *const menu_credits[] = {\n'+',\n'.join(ctext(line) for line in lines)+'\n};\n#endif\n'
    (upstream/'src/menu_art_generated.h').write_text(header)
    intro=[line.strip().split('--',1) for line in (root/'data/introText.txt').read_text().splitlines() if '--' in line]
    if not intro: raise ValueError('No official intro messages')
    (upstream/'src/menu_intro_generated.h').write_text('static const char *const funny_messages[][2] = {\n'+',\n'.join('{'+ctext(a)+','+ctext(b)+'}' for a,b in intro)+'\n};\n')
    menu_files=['story.fbk','freeplay.fbk','merch.fbk','options.fbk','credits.fbk','logo.fbk','titlegf.fbk','back0.fbk','back1.fbk','small.tim']
    manifest=upstream/'funkin.xml'
    xml=ET.parse(manifest)
    directory=xml.find(".//dir[@name='menu']")
    if directory is None: raise ValueError('Disc manifest has no menu directory')
    for filename in menu_files:
        if directory.find(f"file[@name='{filename}']") is None:
            ET.SubElement(directory,'file',name=filename,type='data',source=f'iso/menu/{filename}')
    xml.write(manifest,encoding='utf-8',xml_declaration=True)
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps({'viewport':[320,240],'banks':reports,'credits_lines':len(lines)},indent=2)+'\n')
    print(json.dumps({'banks':len(reports),'bank_bytes':sum((out/f).stat().st_size for f in menu_files if f.endswith('.fbk')),'credits_lines':len(lines)}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--upstream',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();build(a.root,a.upstream,a.report)
