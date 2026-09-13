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
    capture=Capture(upstream);dj_frames=set()
    def screen(selection,time,confirm=-1):
        im=Image.new('RGBA',(320,240),(0,0,0,255))
        for command in reversed(capture.commands(selection,time,confirm)):
            kind,name,*values=command;v=list(map(int,values))
            if kind=='B':
                frame,x,y=v
                if name=='dj.fbk':dj_frames.add(frame)
                im.alpha_composite(bank(name,frame),(x,y))
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
        screen(2,1024).convert('RGB').save(output)
        # Sample just after each 24 Hz boundary. Rounding down then truncating
        # again in C would repeat one frame and skip the next in this preview.
        tick=lambda i:(i*1024+23)//24
        frames=[screen(2,tick(i)) for i in range(73)]
        frames += [screen(2,tick(73+i),tick(i)) for i in range(28)]
        if dj_frames!=set(range(59)):raise ValueError('Preview omitted DJ animation frames')
        # GIF stores centiseconds, so distribute 40/50ms holds to average 24fps.
        durations=[(round((i+1)*100/24)-round(i*100/24))*10 for i in range(len(frames))]
        frames[0].save(output.with_suffix('.gif'),save_all=True,append_images=frames[1:],duration=durations,loop=0,disposal=2)
    finally:capture.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('upstream',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();render(a.upstream,a.output)
