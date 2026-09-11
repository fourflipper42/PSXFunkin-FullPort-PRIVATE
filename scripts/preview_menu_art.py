#!/usr/bin/env python3
"""Render generated PS1 palette pixels for layout review (not an emulator capture)."""
import argparse,json,sys
from pathlib import Path
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parent/'ps1asset'))
from framebank import unpack_indices
from png_to_tim import decode_tim

def render(upstream,report,output):
    root=upstream/'iso/menu'
    records={r['name']:r for r in json.loads(report.read_text())['banks']}
    def bank(name,frame=0):
        w,h,pal,frames=unpack_indices((root/(name+'.fbk')).read_bytes())
        image=Image.new('RGBA',(w,h))
        image.putdata([((pal[i]&31)*255//31,((pal[i]>>5)&31)*255//31,((pal[i]>>10)&31)*255//31,255 if pal[i] else 0) for i in frames[frame]])
        return image
    bg=Image.new('RGBA',(320,240));bg.alpha_composite(bank('back0'));bg.alpha_composite(bank('back1'),(160,0))
    font=decode_tim((root/'small.tim').read_bytes())
    def text(im,s,x,y,center=True):
        if center:x-=len(s)*4
        for c in s:
            i=ord(c)-32;glyph=font.crop(((i%16)*8,(i//16)*12,(i%16)*8+8,(i//16)*12+12))
            shadow=Image.new('RGBA',glyph.size,(0,0,0));shadow.putalpha(glyph.getchannel('A'))
            im.alpha_composite(shadow,(x+1,y+1));im.alpha_composite(glyph,(x,y));x+=8
    screens=[]
    im=Image.new('RGBA',(320,240),(0,0,0,255));im.alpha_composite(bank('logo'),(14,20));im.alpha_composite(bank('titlegf'),(178,74));text(im,'PRESS START TO BEGIN',160,208);screens.append(('TITLE',im))
    for select in (0,4):
        im=bg.copy()
        for i,name in enumerate(['storymode','freeplay','merch','options','credits']):
            rec=records[name];frame=rec['groups'][name+(' selected' if select==i else ' idle')][0]
            label=bank('story' if name=='storymode' else name,frame)
            im.alpha_composite(label,(160-label.width//2,35+i*42-label.height//2))
        screens.append(('MAIN / '+str(select+1),im))
    im=bg.copy()
    for s,y in [('STORY MODE',16),('DUE DEBTS',44),('< WEEKEND 1 >',68),('DARNELL',98),('LIT UP',118),('TWO HOT',138),("BLAZIN'",158),('UP / DOWN: SELECT WEEK',174),('< NORMAL >',196),('X / START: PLAY    O: BACK',216)]:text(im,s,160,y)
    screens.append(('STORY',im))
    sheet=Image.new('RGB',(656,528),(24,24,24));draw=ImageDraw.Draw(sheet)
    for i,(name,im) in enumerate(screens):
        x=(i%2)*328;y=(i//2)*264;draw.text((x+8,y+4),name,fill='white');sheet.paste(im,(x+4,y+20))
    output.parent.mkdir(parents=True,exist_ok=True);sheet.save(output)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('upstream',type=Path);p.add_argument('report',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();render(a.upstream,a.report,a.output)
