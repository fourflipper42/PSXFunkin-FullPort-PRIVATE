#!/usr/bin/env python3
"""Encode Weekend 1 music as PSXFunkin-style 8-channel 2336-byte XA stream."""
from __future__ import annotations
import argparse, subprocess, tempfile, json, shutil, zipfile
from pathlib import Path, PurePosixPath

SECTOR=2336
SONGS={
 'darnell':('darnell',['Voices-pico.ogg','Voices-darnell.ogg']),
 'lit-up':('lit-up',['Voices-pico.ogg','Voices-darnell.ogg']),
 '2hot':('2hot',['Voices-pico.ogg','Voices-darnell.ogg']),
 'blazin':('blazin',[]),
}
DARNELL_INTRO_SOURCES=(
 ('weekend1/music/darnellCanCutscene/darnellCanCutscene.ogg',0),
 ('weekend1/sounds/Darnell_Lighter.ogg',5000),
 ('weekend1/sounds/Gun_Prep.ogg',6000),
 ('weekend1/sounds/Kick_Can_UP.ogg',6400),
 ('weekend1/sounds/Kick_Can_FORWARD.ogg',6900),
 ('weekend1/sounds/shot1.ogg',7100),
 ('weekend1/sounds/cutscene/darnell_laugh.ogg',7900),
 ('weekend1/sounds/cutscene/nene_laugh.ogg',8200),
)

def run(cmd): subprocess.run([str(x) for x in cmd],check=True)

def replace_once(path:Path, old:str, new:str, label:str):
    text=path.read_text()
    count=text.count(old)
    if count!=1:
        raise SystemExit(f'{label}: expected one integrated Erect anchor, found {count}')
    path.write_text(text.replace(old,new,1))

def normalize_erect_audio_layout(upstream:Path):
    """Keep Erect tables aligned while restoring Weekend v2's proven append anchors.

    Erect/Nightmare is applied before Weekend 1 in the combined pipeline. Its
    file IDs and track IDs originally append at the same legacy anchors Weekend
    v2 uses. Move each Erect block together with its matching path/length block
    so Weekend can append afterwards without changing any symbolic routing.
    """
    audio_h=upstream/'src/audio.h'
    audio_c=upstream/'src/audio.c'

    file_block=(
        '\tXA_ErectA, //ERECTA.XA\n'
        '\tXA_ErectB, //ERECTB.XA\n'
        '\tXA_ErectC, //ERECTC.XA\n'
        '\tXA_ErectD, //ERECTD.XA\n'
    )
    replace_once(
        audio_h,
        '\tXA_ClwnB,  //CLWNB.XA\n'+file_block+'\t\n\tXA_Max,',
        file_block+'\tXA_ClwnB,  //CLWNB.XA\n\t\n\tXA_Max,',
        'Erect XA file normalization',
    )

    track_block=(
        '\t//ERECTA.XA\n'
        '\tXA_Erect_Bopeebo,\n'
        '\tXA_Erect_Fresh,\n'
        '\tXA_Erect_Dadbattle,\n'
        '\tXA_Erect_Spookeez,\n'
        '\t//ERECTB.XA\n'
        '\tXA_Erect_South,\n'
        '\tXA_Erect_Pico,\n'
        '\tXA_Erect_Philly,\n'
        '\tXA_Erect_Blammed,\n'
        '\t//ERECTC.XA\n'
        '\tXA_Erect_SatinPanties,\n'
        '\tXA_Erect_High,\n'
        '\tXA_Erect_Cocoa,\n'
        '\tXA_Erect_Eggnog,\n'
        '\t//ERECTD.XA\n'
        '\tXA_Erect_Senpai,\n'
        '\tXA_Erect_Roses,\n'
        '\tXA_Erect_Thorns,\n'
        '\tXA_Erect_Ugh,\n'
    )
    legacy_tracks=(
        '\tXA_Hellclown,   //Hellclown\n'
        '\tXA_Expurgation, //Expurgation\n'
    )
    replace_once(
        audio_h,
        legacy_tracks+track_block+'} XA_Track;',
        track_block+legacy_tracks+'} XA_Track;',
        'Erect XA track normalization',
    )

    length_block=(
        '\t//ERECTA.XA\n'
        '\t{XA_ErectA, ERECT_BOPEEBO_SECTORS * IO_SECT_SIZE}, //XA_Erect_Bopeebo\n'
        '\t{XA_ErectA, ERECT_FRESH_SECTORS * IO_SECT_SIZE}, //XA_Erect_Fresh\n'
        '\t{XA_ErectA, ERECT_DADBATTLE_SECTORS * IO_SECT_SIZE}, //XA_Erect_Dadbattle\n'
        '\t{XA_ErectA, ERECT_SPOOKEEZ_SECTORS * IO_SECT_SIZE}, //XA_Erect_Spookeez\n'
        '\t//ERECTB.XA\n'
        '\t{XA_ErectB, ERECT_SOUTH_SECTORS * IO_SECT_SIZE}, //XA_Erect_South\n'
        '\t{XA_ErectB, ERECT_PICO_SECTORS * IO_SECT_SIZE}, //XA_Erect_Pico\n'
        '\t{XA_ErectB, ERECT_PHILLY_SECTORS * IO_SECT_SIZE}, //XA_Erect_Philly\n'
        '\t{XA_ErectB, ERECT_BLAMMED_SECTORS * IO_SECT_SIZE}, //XA_Erect_Blammed\n'
        '\t//ERECTC.XA\n'
        '\t{XA_ErectC, ERECT_SATINPANTIES_SECTORS * IO_SECT_SIZE}, //XA_Erect_SatinPanties\n'
        '\t{XA_ErectC, ERECT_HIGH_SECTORS * IO_SECT_SIZE}, //XA_Erect_High\n'
        '\t{XA_ErectC, ERECT_COCOA_SECTORS * IO_SECT_SIZE}, //XA_Erect_Cocoa\n'
        '\t{XA_ErectC, ERECT_EGGNOG_SECTORS * IO_SECT_SIZE}, //XA_Erect_Eggnog\n'
        '\t//ERECTD.XA\n'
        '\t{XA_ErectD, ERECT_SENPAI_SECTORS * IO_SECT_SIZE}, //XA_Erect_Senpai\n'
        '\t{XA_ErectD, ERECT_ROSES_SECTORS * IO_SECT_SIZE}, //XA_Erect_Roses\n'
        '\t{XA_ErectD, ERECT_THORNS_SECTORS * IO_SECT_SIZE}, //XA_Erect_Thorns\n'
        '\t{XA_ErectD, ERECT_UGH_SECTORS * IO_SECT_SIZE}, //XA_Erect_Ugh\n'
    )
    legacy_lengths=(
        '\t{XA_ClwnB, XA_LENGTH(21886)}, //XA_Hellclown\n'
        '\t{XA_ClwnB, XA_LENGTH(19607)}, //XA_Expurgation\n'
    )
    replace_once(
        audio_c,
        legacy_lengths+length_block+'};',
        length_block+legacy_lengths+'};',
        'Erect XA length normalization',
    )

    path_block=(
        '\t\t"\\\\MUSIC\\\\ERECTA.XA;1", //XA_ErectA\n'
        '\t\t"\\\\MUSIC\\\\ERECTB.XA;1", //XA_ErectB\n'
        '\t\t"\\\\MUSIC\\\\ERECTC.XA;1", //XA_ErectC\n'
        '\t\t"\\\\MUSIC\\\\ERECTD.XA;1", //XA_ErectD\n'
    )
    clwnb='\t\t"\\\\MUSIC\\\\CLWNB.XA;1",  //XA_ClwnB\n'
    replace_once(
        audio_c,
        clwnb+path_block,
        path_block+clwnb,
        'Erect XA path normalization',
    )

    # The four parallel structures must remain index-aligned after reordering.
    h=audio_h.read_text(); c=audio_c.read_text()
    for marker in ('XA_ErectA','XA_Erect_Ugh','XA_ClwnB'):
        if marker not in h or marker not in c:
            raise SystemExit(f'integrated Erect audio normalization lost {marker}')
    if '\tXA_ClwnB,  //CLWNB.XA\n\t\n\tXA_Max' not in h:
        raise SystemExit('Weekend XA file append anchor was not restored')
    if '\tXA_Expurgation, //Expurgation\n} XA_Track;' not in h:
        raise SystemExit('Weekend XA track append anchor was not restored')
    if '\t{XA_ClwnB, XA_LENGTH(19607)}, //XA_Expurgation\n};' not in c:
        raise SystemExit('Weekend XA length append anchor was not restored')
    print('Normalized integrated Erect XA layout for Weekend 1 append')

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

def ensure_darnell_intro_sources(root:Path):
    """Recover exact official v0.8.4 Weekend intro audio omitted by split asset caches."""
    missing=[rel for rel,_ in DARNELL_INTRO_SOURCES if not (root/rel).is_file() or (root/rel).stat().st_size==0]
    if not missing:
        return

    archive=root.parent/'official-assets'/'funkin-linux-64bit.zip'
    if not archive.is_file():
        joined=', '.join(missing)
        raise FileNotFoundError(f'Weekend 1 intro sources missing ({joined}); official v0.8.4 Linux archive not found at {archive}')

    with zipfile.ZipFile(archive) as z:
        files=[n for n in z.namelist() if not n.endswith('/') and not z.getinfo(n).is_dir()]
        for rel in missing:
            suffix=('assets/'+PurePosixPath(rel).as_posix()).lower()
            matches=[n for n in files if n.lower().endswith(suffix)]
            if not matches:
                raise FileNotFoundError(f'official v0.8.4 Weekend 1 source missing from pinned archive: {suffix}')
            name=sorted(matches,key=lambda n:(len(PurePosixPath(n).parts),len(n),n.lower()))[0]
            out=root/rel
            out.parent.mkdir(parents=True,exist_ok=True)
            with z.open(name) as src, out.open('wb') as dst:
                shutil.copyfileobj(src,dst)
            if out.stat().st_size==0:
                raise ValueError(f'extracted empty official Weekend 1 source: {name}')

    still_missing=[rel for rel,_ in DARNELL_INTRO_SOURCES if not (root/rel).is_file() or (root/rel).stat().st_size==0]
    if still_missing:
        raise FileNotFoundError('Weekend 1 intro source recovery incomplete: '+', '.join(still_missing))

def make_darnell_intro_mix(ffmpeg:Path,root:Path,out:Path):
    ensure_darnell_intro_sources(root)
    sources=[(root/rel,delay) for rel,delay in DARNELL_INTRO_SOURCES]
    cmd=[ffmpeg,'-y','-loglevel','error']
    for path,_ in sources: cmd += ['-i',path]
    filters=[]; labels=[]
    for i,(_,delay) in enumerate(sources):
        label=f'a{i}'; filters.append(f'[{i}:a]adelay={delay}|{delay}[{label}]'); labels.append(f'[{label}]')
    filters.append(''.join(labels)+f'amix=inputs={len(labels)}:duration=longest:normalize=0[mix]')
    cmd += ['-filter_complex',';'.join(filters),'-map','[mix]','-ar','18900','-ac','2',out]
    run(cmd)

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
  intro_wav=t/'darnell-intro.wav'; make_darnell_intro_mix(a.ffmpeg,a.root,intro_wav)
  intro_xa=a.out/'darnin.xa'; enc(a.psxavenc,intro_wav,intro_xa,0)
  rep['darnin.xa']={'bytes':intro_xa.stat().st_size,'sample_rate':18900,'channel':0,'official_sfx_mix':True,'official_source_count':len(DARNELL_INTRO_SOURCES)}
 normalize_erect_audio_layout(a.out.parent.parent)
 a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(rep,indent=2)+'\n'); print(json.dumps(rep,indent=2))

if __name__=='__main__': main()
