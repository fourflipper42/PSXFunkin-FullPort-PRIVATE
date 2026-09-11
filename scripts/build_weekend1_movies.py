#!/usr/bin/env python3
"""Encode complete 24 fps Weekend 1 footage, letterboxed in a 4:3 viewport."""
from __future__ import annotations
import argparse,json,struct,subprocess,tempfile
from fractions import Fraction
from pathlib import Path
MOVIES=[('darnellCutscene.mp4','darnell.str','W1_DARNELL_FRAMES'),('2hotCutscene.mp4','2hot.str','W1_2HOT_FRAMES'),('blazinCutscene.mp4','blazin.str','W1_BLAZIN_FRAMES')]
SECTOR=2336
STR_MAGIC=b'\x60\x01\x01\x80'
def run(command):subprocess.run([str(x) for x in command],check=True)
def inspect_str(path:Path):
    data=path.read_bytes()
    if not data or len(data)%SECTOR:raise ValueError(f'{path}: incomplete sectors')
    frame=chunk=chunks=0
    dimensions=None
    quant=[]
    for offset in range(0,len(data),SECTOR):
        sec=data[offset:offset+SECTOR]
        if sec[2]!=0x48 or sec[8:12]!=STR_MAGIC:continue
        index,count,number=struct.unpack_from('<HHI',sec,12)
        size=struct.unpack_from('<HH',sec,24)
        if dimensions is None:dimensions=size
        if size!=dimensions:raise ValueError(f'{path}: changing frame dimensions')
        if index==0:
            if chunk!=chunks or number!=frame+1:raise ValueError(f'{path}: incomplete or missing frame')
            frame=number;chunk=0;chunks=count
            quant.append(struct.unpack_from('<H',sec,44)[0])
        if not count or number!=frame or count!=chunks or index!=chunk:raise ValueError(f'{path}: invalid chunk sequence')
        chunk+=1
    if not frame or chunk!=chunks:raise ValueError(f'{path}: no complete final frame')
    return {'frames':frame,'dimensions':list(dimensions),'quant_scale_mean':sum(quant)/len(quant),'quant_scale_max':max(quant),'sectors':len(data)//SECTOR}
def raw_cd_stream(source:Path,target:Path):
    # FFmpeg's PSX demuxer expects raw 2352-byte sectors. The authoring tool
    # supplies these headers on disc; add them here solely for decode testing.
    data=source.read_bytes()
    if len(data)%SECTOR:raise ValueError('Incomplete sector')
    def bcd(n):return (n//10)*16+n%10
    with target.open('wb') as out:
        for offset in range(0,len(data),SECTOR):
            lba=offset//SECTOR+150
            out.write(b'\0'+b'\xff'*10+b'\0'+bytes((bcd(lba//4500),bcd(lba//75%60),bcd(lba%75),2)))
            out.write(data[offset:offset+SECTOR])
def verify_software_decode(source:Path,expected:int,ffprobe='ffprobe'):
    with tempfile.TemporaryDirectory() as td:
        raw=Path(td)/'verify.str';raw_cd_stream(source,raw)
        result=subprocess.run([ffprobe,'-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=codec_name,width,height,nb_read_frames','-of','json',str(raw)],text=True,capture_output=True,check=True)
        if result.stderr.strip():raise ValueError(f'MDEC decode failed: {result.stderr}')
        stream=json.loads(result.stdout)['streams'][0]
        if stream['codec_name']!='mdec' or int(stream['nb_read_frames'])!=expected:raise ValueError(f'MDEC decoded frame mismatch: {stream}')
        return int(stream['nb_read_frames'])
def encoded_frame_count(path:Path)->int:return inspect_str(path)['frames']
def encode_movie(source:Path,out:Path,encoder:Path,ffmpeg='ffmpeg',ffprobe='ffprobe'):
    result=subprocess.run([ffprobe,'-v','error','-select_streams','v:0','-show_entries','stream=width,height,avg_frame_rate,nb_frames,duration','-of','json',str(source)],check=True,capture_output=True,text=True)
    probe=json.loads(result.stdout)['streams'][0]
    fps=Fraction(probe['avg_frame_rate'])
    if fps!=24:raise ValueError(f'{source}: expected pinned 24 fps source, got {fps}')
    if probe['width']*9!=probe['height']*16:raise ValueError(f'{source}: expected pinned 16:9 footage')
    expected=int(probe['nb_frames'])
    with tempfile.TemporaryDirectory() as td:
        # NUT retains exact rational timestamps; millisecond-rounded container
        # timestamps can introduce spurious frame duplicates in resamplers.
        padded=Path(td)/'letterboxed.nut'
        run([ffmpeg,'-y','-v','error','-i',source,'-map','0:v:0','-map','0:a:0','-vf','scale=320:180:flags=lanczos,pad=320:240:0:30:black,setsar=1','-c:v','ffv1','-pix_fmt','yuv420p','-c:a','pcm_s16le',padded])
        run([encoder,'-q','-t','str','-v','v2','-f','37800','-b','4','-c','2','-s','320x240','-r','24','-x','2',padded,out])
    stats=inspect_str(out)
    if stats['frames']!=expected:raise ValueError(f'{out}: encoded {stats["frames"]} frames, source has {expected}')
    if stats['dimensions']!=[320,240]:raise ValueError(f'{out}: unexpected viewport')
    decoded=verify_software_decode(out,expected,ffprobe)
    return {**stats,'software_decoded_frames':decoded,'source':source.name,'file':out.name,'source_frames':expected,'source_fps':24,'encoded_fps':24,'frames_dropped':0,'source_duration':float(probe['duration']),'picture':[320,180],'letterbox_top':30,'bytes':out.stat().st_size,'sector_size':SECTOR}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('root','out','psxavenc','report','header'):p.add_argument('--'+flag,type=Path,required=True)
    p.add_argument('--ffprobe',default='ffprobe');p.add_argument('--ffmpeg',default='ffmpeg');a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True);reports=[];defines=[]
    for name,dest,define in MOVIES:
        r=encode_movie(a.root/'videos/videos'/name,a.out/dest,a.psxavenc,a.ffmpeg,a.ffprobe)
        reports.append(r);defines.append(f'#define {define} {r["frames"]}')
    a.header.parent.mkdir(parents=True,exist_ok=True)
    a.header.write_text('#ifndef _WEEKEND1_MOVIES_GENERATED_H\n#define _WEEKEND1_MOVIES_GENERATED_H\n'+'\n'.join(defines)+'\n#endif\n')
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(reports,indent=2)+'\n');print(json.dumps(reports,indent=2))
if __name__=='__main__':main()
