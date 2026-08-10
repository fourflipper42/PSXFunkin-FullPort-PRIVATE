#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, struct, subprocess
from pathlib import Path
MOVIES=[
 ('darnellCutscene.mp4','darnell.str','W1_DARNELL_FRAMES'),
 ('2hotCutscene.mp4','2hot.str','W1_2HOT_FRAMES'),
 ('blazinCutscene.mp4','blazin.str','W1_BLAZIN_FRAMES'),
]
SECTOR=2336
STR_MAGIC=b'\x60\x01\x01\x80'
def run(c): subprocess.run([str(x) for x in c],check=True,capture_output=False)
def encoded_frame_count(path:Path)->int:
 b=path.read_bytes(); mx=0
 if len(b)%SECTOR: raise RuntimeError(f'{path} is not 2336-byte sector aligned')
 for off in range(0,len(b),SECTOR):
  sec=b[off:off+SECTOR]
  # XA subheader occupies the first 8 bytes.  PSX STR video sectors use
  # real-time data submode 0x48; the MDEC header follows immediately.
  if sec[2] == 0x48 and sec[8:12] == STR_MAGIC:
   mx=max(mx,struct.unpack_from('<I',sec,16)[0])
 if mx <= 0: raise RuntimeError(f'no STR video frames found in {path}')
 return mx

def patch_m1_v4_helper()->None:
 # M1 v4 removes the two unguarded operations that previously happened before
 # PlayStr(): a redundant movie lookup and an infinite PADstart-release wait.
 # Rewrite the helper's complete Movie_Play template structurally instead of
 # matching its whitespace-sensitive C body.
 helper=Path(__file__).with_name('apply_iso9660_lookup_fallback.py')
 text=helper.read_text()
 if 'M1_MOVIE_ENTRY_V4' in text:
  return
 start_marker="    movie_play = r'''void Movie_Play("
 start=text.find(start_marker)
 if start < 0:
  raise RuntimeError('M1 v4 Movie_Play template start missing')
 end=text.find("\n'''", start + len(start_marker))
 if end < 0:
  raise RuntimeError('M1 v4 Movie_Play template end missing')
 end += len("\n'''")
 replacement=r'''    movie_play = r\'''void Movie_Play(const char *path, unsigned long length)
{
\tAudio_StopXA();

\t/* M1_MOVIE_ENTRY_V4
\t * Do not perform an unguarded preflight CdSearchFile/ISO scan here and do
\t * not spin waiting for PADstart. strDoPlayback owns bounded lookup/CD
\t * startup and reports E0-E4. Start is sampled only after playback begins. */
\tSTRFILE sfile;
\tstrcpy(sfile.FileName, path);
\tsfile.Xres = 320;
\tsfile.Yres = 240;
\tsfile.NumFrames = length;
\tPlayStr(320, 240, 0, 0, &sfile);

\tCdControlB(CdlPause, NULL, NULL);
\tDrawSync(0);
\tSetDispMask(1);
}
\''' '''
 # The replacement above is constructed without relying on the C body's tabs.
 # Normalize the escaped Python triple-quote delimiters into the helper source.
 replacement=replacement.replace("r\\'''", "r'''").replace("\\''' ", "'''")
 text=text[:start]+replacement+text[end:]
 helper.write_text(text)
 print('M1 v4: structurally rewrote Movie_Play without preflight lookup/Start wait')

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); ap.add_argument('--psxavenc',type=Path,required=True); ap.add_argument('--ffprobe',default='ffprobe'); ap.add_argument('--report',type=Path,required=True); ap.add_argument('--header',type=Path,required=True); a=ap.parse_args(); a.out.mkdir(parents=True,exist_ok=True); r=[]; defines=[]
 patch_m1_v4_helper()
 for srcname,outname,define in MOVIES:
  src=a.root/'videos/videos'/srcname; out=a.out/outname
  run([a.psxavenc,'-q','-t','str','-v','v2','-f','37800','-b','4','-c','2','-s','320x240','-r','15','-x','2',src,out])
  frames=encoded_frame_count(out)
  d=float(subprocess.run([str(a.ffprobe),'-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(src)],check=True,text=True,capture_output=True).stdout.strip())
  r.append({'source':srcname,'file':outname,'frames':frames,'source_duration':d,'bytes':out.stat().st_size,'sector_size':SECTOR})
  defines.append(f'#define {define} {frames}')
 a.header.parent.mkdir(parents=True,exist_ok=True); a.header.write_text('#ifndef _WEEKEND1_MOVIES_GENERATED_H\n#define _WEEKEND1_MOVIES_GENERATED_H\n'+'\n'.join(defines)+'\n#endif\n')
 a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(r,indent=2)+'\n'); print(json.dumps(r,indent=2))
if __name__=='__main__': main()
