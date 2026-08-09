#!/usr/bin/env python3
"""Encode Weekend 1 music as PSXFunkin-style 8-channel 2336-byte XA stream."""
from __future__ import annotations
import argparse, subprocess, tempfile, json
from pathlib import Path
SECTOR=2336
SONGS={
 'darnell':('darnell',['Voices-pico.ogg','Voices-darnell.ogg']),
 'lit-up':('lit-up',['Voices-pico.ogg','Voices-darnell.ogg']),
 '2hot':('2hot',['Voices-pico.ogg','Voices-darnell.ogg']),
 'blazin':('blazin',[]),
}
def run(cmd): subprocess.run([str(x) for x in cmd],check=True)
def make_mix(ffmpeg:Path, sdir:Path, voices:list[str], out:Path):
    inst=sdir/'Inst.ogg'
    if not voices:
        run([ffmpeg,'-y','-loglevel','error','-i',inst,'-ar','18900','-ac','2',out]); return
    cmd=[ffmpeg,'-y','-loglevel','error','-i',inst]
    for v in voices: cmd += ['-i',sdir/v]
    n=1+len(voices); inputs=''.join(f'[{i}:a]' for i in range(n))
    cmd += ['-filter_complex',f'{inputs}amix=inputs={n}:duration=longest:normalize=0[a]','-map','[a]','-ar','18900','-ac','2',out]
    run(cmd)
def enc(enc:Path, inp:Path, out:Path, chan:int): run([enc,'-q','-t','xa','-f','18900','-b','4','-c','2','-F','1','-C',str(chan),inp,out])
def sectors(path:Path):
    b=path.read_bytes()
    if len(b)%SECTOR: raise ValueError(f'{path} not 2336-sector aligned')
    return [b[i:i+SECTOR] for i in range(0,len(b),SECTOR)]
def interleave(out:Path, paths:list[Path], silence:list[bytes]):
    streams=[sectors(p) for p in paths]; count=max(map(len,streams)); data=bytearray()
    for i in range(count):
        for ch,st in enumerate(streams): data += st[i] if i<len(st) else silence[ch]
    out.parent.mkdir(parents=True,exist_ok=True); out.write_bytes(data)
    return count*8

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); ap.add_argument('--psxavenc',type=Path,required=True); ap.add_argument('--ffmpeg',type=Path,default=Path('ffmpeg')); ap.add_argument('--report',type=Path,required=True); a=ap.parse_args()
 a.out.mkdir(parents=True,exist_ok=True); rep={}
 with tempfile.TemporaryDirectory() as td:
  t=Path(td)
  silent=t/'silence.wav'; run([a.ffmpeg,'-y','-loglevel','error','-f','lavfi','-i','anullsrc=r=18900:cl=stereo','-t','1',silent])
  sil=[]
  for ch in range(8):
   p=t/f'sil{ch}.xa'; enc(a.psxavenc,silent,p,ch); sil.append(sectors(p)[0])
  for song,(folder,voices) in SONGS.items():
   sdir=a.root/'songs'/folder; full=t/f'{song}-full.wav'; inst=t/f'{song}-inst.wav'
   make_mix(a.ffmpeg,sdir,voices,full); run([a.ffmpeg,'-y','-loglevel','error','-i',sdir/'Inst.ogg','-ar','18900','-ac','2',inst]); rep[song]={'voices':voices}
  assignments=[('darnell',0),('lit-up',2),('2hot',4),('blazin',6)]; mapping=[None]*8
  for song,base in assignments:
   pfull=t/f'{song}-full.xa'; pinst=t/f'{song}-inst.xa'; enc(a.psxavenc,t/f'{song}-full.wav',pfull,base); enc(a.psxavenc,t/f'{song}-inst.wav',pinst,base+1); mapping[base]=pfull; mapping[base+1]=pinst
  name='week8.xa'; total=interleave(a.out/name,mapping,sil); rep[name]={'physical_sectors':total,'bytes':(a.out/name).stat().st_size,'sample_rate':18900,'channels':8}
 a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(rep,indent=2)+'\n'); print(json.dumps(rep,indent=2))
if __name__=='__main__': main()
