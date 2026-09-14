#!/usr/bin/env python3
"""Integration check of source frame count, letterboxing and complete STR chunks."""
import argparse,json,subprocess,tempfile
from pathlib import Path
from build_weekend1_movies import encode_movie,inspect_str,SECTOR,STR_MAGIC

def check(encoder):
    reports=[]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        for count in (1,24,61):
            source=root/f'{count}.mp4';out=root/f'{count}.str'
            subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=24','-f','lavfi','-i','sine=frequency=440:sample_rate=37800','-t',str(count/24),'-frames:v',str(count),'-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True)
            result=encode_movie(source,out,encoder)
            if result['frames']!=count:raise AssertionError(result)
            reports.append(result)
        data=out.read_bytes()
        starts=[i for i in range(0,len(data),SECTOR) if data[i+2]==0x48 and data[i+8:i+12]==STR_MAGIC]
        bad=root/'truncated.str';last=starts[-1];bad.write_bytes(data[:last]+data[last+SECTOR:])
        try:inspect_str(bad)
        except ValueError:pass
        else:raise AssertionError('Incomplete last frame accepted')
    print(json.dumps(reports,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('encoder',type=Path);check(p.parse_args().encoder.resolve())
