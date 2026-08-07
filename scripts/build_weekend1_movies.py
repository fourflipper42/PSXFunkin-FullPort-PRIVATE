#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path
MOVIES=[('darnellCutscene.mp4','darnell.str'),('2hotCutscene.mp4','2hot.str'),('blazinCutscene.mp4','blazin.str')]
def run(c): subprocess.run([str(x) for x in c],check=True,capture_output=False)
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); ap.add_argument('--psxavenc',type=Path,required=True); ap.add_argument('--ffprobe',default='ffprobe'); ap.add_argument('--report',type=Path,required=True); a=ap.parse_args(); a.out.mkdir(parents=True,exist_ok=True); r=[]
 for srcname,outname in MOVIES:
  src=a.root/'videos/videos'/srcname; out=a.out/outname
  # mkpsxiso's mixed/XA/STR importer expects 2336-byte sector payloads and
  # rebuilds absolute-address EDC/ECC during mastering.  Do not use strcd here.
  run([a.psxavenc,'-q','-t','str','-v','v2','-f','37800','-b','4','-c','2','-s','320x240','-r','15','-x','2',src,out])
  if out.stat().st_size % 2336:
   raise RuntimeError(f'{out} is not 2336-byte sector aligned')
  d=float(subprocess.run([str(a.ffprobe),'-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(src)],check=True,text=True,capture_output=True).stdout.strip()); n=round(d*15)
  r.append({'source':srcname,'file':outname,'frames':n,'duration':d,'bytes':out.stat().st_size,'sector_size':2336})
 a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(r,indent=2)+'\n'); print(json.dumps(r,indent=2))
if __name__=='__main__': main()
