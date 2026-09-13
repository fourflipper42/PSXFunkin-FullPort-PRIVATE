#!/usr/bin/env python3
"""Render actual C Freeplay graphics calls using converted palette pixels.

This verifies layout and frame selection, not GPU behavior or hardware timing.
"""
import argparse,sys
from pathlib import Path
from PIL import Image
from capture_freeplay import Capture
sys.path.insert(0,str(Path(__file__).resolve().parent/'ps1asset'))
from framebank import unpack_indices
from png_to_tim import decode_tim

def render(upstream,output):
    root=upstream/'iso/freeplay';cache={}
    def bank(name,index):
        if (name,index) in cache:return cache[name,index]
        w,h,pal,frames=unpack_indices((root/name).read_bytes())
        im=Image.new('RGBA',(w,h));im.putdata([((pal[i]&31)*255//31,((pal[i]>>5)&31)*255//31,((pal[i]>>10)&31)*255//31,255 if pal[i] else 0) for i in frames[index]])
        cache[name,index]=im;return im
    capture=Capture(upstream)
    def screen(selection,time,confirm=-1):
        im=Image.new('RGBA',(320,240),(0,0,0,255))
        for command in reversed(capture.commands(selection,time,confirm)):
            kind,name,*values=command;v=list(map(int,values))
            if kind=='B':
                frame,x,y=v;im.alpha_composite(bank(name,frame),(x,y))
            else:
                x,y,sx,sy,w,h,r,g,b=v
                if name not in cache:cache[name]=decode_tim((root/name).read_bytes())
                glyph=cache[name].crop((sx,sy,sx+w,sy+h))
                channels=list(glyph.split())
                for i,gain in enumerate((r,g,b)):channels[i]=channels[i].point(lambda pixel:min(255,pixel*gain//128))
                im.alpha_composite(Image.merge('RGBA',channels),(x,y))
        return im
    try:
        output.parent.mkdir(parents=True,exist_ok=True)
        screen(1,1024).convert('RGB').save(output)
        frames=[screen(1,i*1024//24) for i in range(73)]
        frames += [screen(1,(73+i)*1024//24,i*1024//24) for i in range(28)]
        frames[0].save(output.with_suffix('.gif'),save_all=True,append_images=frames[1:],duration=42,loop=0,disposal=2)
    finally:capture.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('upstream',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();render(a.upstream,a.output)
