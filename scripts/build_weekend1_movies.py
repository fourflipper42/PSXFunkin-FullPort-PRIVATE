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
 # matching its whitespace-sensitive C body. Keep every final validator in
 # lock-step so Pico's integration pass validates the v4 contract rather than
 # rejecting the intentional removal of the v3 wrapper preflight.
 helper=Path(__file__).with_name('apply_iso9660_lookup_fallback.py')
 text=helper.read_text()
 validator_marker='M1 v4 redundant preflight ISO search survived'
 if 'M1_MOVIE_ENTRY_V4' not in text:
  start_marker="    movie_play = r'''void Movie_Play("
  start=text.find(start_marker)
  if start < 0:
   raise RuntimeError('M1 v4 Movie_Play template start missing')
  end=text.find("\n'''", start + len(start_marker))
  if end < 0:
   raise RuntimeError('M1 v4 Movie_Play template end missing')
  end += len("\n'''")
  replacement=r"""    movie_play = r'''void Movie_Play(const char *path, unsigned long length)
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
'''"""
  # Keep Python quoting literal while normalizing C indentation.
  replacement=replacement.replace("\\t", "\t")
  text=text[:start]+replacement+text[end:]
 old_validation='''    if "IO_SearchFile(&file, path)" not in movie:\n        raise SystemExit("Movie_Play does not use full ISO search")\n'''
 new_validation='''    if "M1_MOVIE_ENTRY_V4" not in movie:\n        raise SystemExit("M1 v4 movie entry marker missing")\n    if "IO_SearchFile(&file, path)" in movie:\n        raise SystemExit("M1 v4 redundant preflight ISO search survived")\n    if "while (PadRead(1) & PADstart)" in movie:\n        raise SystemExit("M1 v4 unbounded Start-release wait survived")\n'''
 if old_validation in text:
  text=text.replace(old_validation,new_validation,1)
 elif validator_marker not in text:
  raise RuntimeError('M1 v4 validator anchor missing')
 helper.write_text(text)

 # build_pico_mix_movies.py injects the final post-apply validator into the Pico
 # apply script. Its v3-era Movie_Play check must match the same M1 v4 contract:
 # Movie_Play delegates lookup to bounded strDoPlayback instead of doing a
 # second unguarded resolver pass before PlayStr().
 pico_builder=Path(__file__).with_name('build_pico_mix_movies.py')
 pico=pico_builder.read_text()
 old_key='            "Movie resolver": "IO_SearchFile(&file, path)",'
 new_key='            "Movie entry v4": "M1_MOVIE_ENTRY_V4",'
 if old_key in pico:
  pico=pico.replace(old_key,new_key,1)
 old_guard='''        if _runtime_required["Movie resolver"] not in _runtime_movie:
            _pico_fail("M1/M3 validation", "Movie_Play is not using the shared resolver")
'''
 new_guard='''        if _runtime_required["Movie entry v4"] not in _runtime_movie:
            _pico_fail("M1/M3 validation", "M1 v4 movie entry marker missing")
        if "IO_SearchFile(&file, path)" in _runtime_movie:
            _pico_fail("M1/M3 validation", "M1 v4 redundant preflight ISO search survived")
        if "while (PadRead(1) & PADstart)" in _runtime_movie:
            _pico_fail("M1/M3 validation", "M1 v4 unbounded Start-release wait survived")
'''
 if old_guard in pico:
  pico=pico.replace(old_guard,new_guard,1)
 elif 'M1 v4 redundant preflight ISO search survived' not in pico:
  raise RuntimeError('M1 v4 Pico validator anchor missing')
 pico_builder.write_text(pico)

 # Temporary M1 acceptance build: patch the generated Pico apply step so the
 # final runtime tree boots directly through one known-good STR before any
 # Weekend/SP story state. After Movie_Play returns, normal menu startup is
 # untouched. This keeps the large-disc lookup conditions while isolating the
 # generic movie subsystem for emulator/hardware testing.
 pico_apply=Path(__file__).with_name('apply_pico_mixes_v1.py')
 apply_text=pico_apply.read_text()
 diag_marker='M1_ISOLATED_STR_BOOT_SCRIPT_V1'
 if diag_marker not in apply_text:
  diag_anchor='    print("Applied all 15 official Pico Mixes, Pico Freeplay routing, runtime events, and ISO9660 lookup fallback")\n'
  if apply_text.count(diag_anchor) != 1:
   raise RuntimeError(f'M1 diagnostic apply anchor changed: {apply_text.count(diag_anchor)}')
  diag_insert=r'''    # M1_ISOLATED_STR_BOOT_SCRIPT_V1
    diag_header = root / "src/pico_mix_movies_generated.h"
    frame_prefix = "#define PICO_STRESS_INTRO_FRAMES "
    frame_lines = [line for line in diag_header.read_text().splitlines() if line.startswith(frame_prefix)]
    if len(frame_lines) != 1:
        raise SystemExit(f"M1 diagnostic frame macro count changed: {len(frame_lines)}")
    diag_frames = int(frame_lines[0][len(frame_prefix):].strip())

    diag_main_path = root / "src/main.c"
    diag_main = diag_main_path.read_text()
    if "M1_ISOLATED_STR_BOOT_V1" not in diag_main:
        if '#include "movie.h"\n' not in diag_main:
            diag_main = once(
                diag_main,
                '#include "stage.h"\n',
                '#include "stage.h"\n#include "movie.h"\n',
                "M1 diagnostic movie include",
            )
        timer_anchor = "\tTimer_Init();\n\t\n\t//Start game"
        timer_patch = (
            "\tTimer_Init();\n"
            "\n"
            "\t/* M1_ISOLATED_STR_BOOT_V1: direct generic STR acceptance test. */\n"
            f'\tMovie_Play("\\\\MOVIE\\\\PSTRS.STR;1", {diag_frames});\n'
            "\n"
            "\t//Start game"
        )
        diag_main = once(diag_main, timer_anchor, timer_patch, "M1 diagnostic boot hook")
        diag_main_path.write_text(diag_main)

'''
  apply_text=apply_text.replace(diag_anchor,diag_insert+diag_anchor,1)
  pico_apply.write_text(apply_text)
 print('M1 v4: rewrote Movie_Play, aligned validators, and installed isolated STR boot diagnostic')

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
