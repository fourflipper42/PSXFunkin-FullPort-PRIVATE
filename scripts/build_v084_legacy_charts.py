#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path

MAPPING=[('tutorial',1,4),('bopeebo',1,1),('fresh',1,2),('dadbattle',1,3),('spookeez',2,1),('south',2,2),('monster',2,3),('pico',3,1),('philly-nice',3,2),('blammed',3,3),('satin-panties',4,1),('high',4,2),('milf',4,3),('cocoa',5,1),('eggnog',5,2),('winter-horrorland',5,3),('senpai',6,1),('roses',6,2),('thorns',6,3),('ugh',7,1),('guns',7,2),('stress',7,3)]
BASE_DIFFS=(('easy','e'),('normal','n'),('hard','h'))
EXTRA_DIFFS=(('erect','r'),('nightmare','m'))

def load_chartc(path:Path):
    spec=importlib.util.spec_from_file_location('psxfunkin_chartc_v2',path); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod

def sha256(p:Path):
    h=hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data-root',type=Path,required=True); ap.add_argument('--iso-root',type=Path,required=True); ap.add_argument('--manifest',type=Path,required=True); a=ap.parse_args()
    chartc=load_chartc(Path(__file__).with_name('psxfunkin_chartc_v2.py')); songs_root=a.data_root/'data'/'songs'; outdir=a.iso_root/'chart'; outdir.mkdir(parents=True,exist_ok=True); records=[]
    for song,week,index in MAPPING:
        sdir=songs_root/song; base_chart=sdir/f'{song}-chart.json'; base_meta=sdir/f'{song}-metadata.json'
        if not base_chart.exists() or not base_meta.exists(): raise SystemExit(f'missing base chart/meta for {song}')
        chart=json.loads(base_chart.read_text()); meta=json.loads(base_meta.read_text())
        for diff,suffix in BASE_DIFFS:
            payload=chartc.convert(chart,meta,diff); out=outdir/f'{week}.{index}{suffix}.cht'; out.write_bytes(payload); records.append({'song':song,'variation':'bf','difficulty':diff,'file':out.name,'bytes':len(payload),'sha256':sha256(out)})
        erect_chart=sdir/f'{song}-chart-erect.json'; erect_meta=sdir/f'{song}-metadata-erect.json'
        if erect_chart.exists() and erect_meta.exists():
            chart=json.loads(erect_chart.read_text()); meta=json.loads(erect_meta.read_text())
            for diff,suffix in EXTRA_DIFFS:
                if diff not in chart.get('notes',{}): continue
                payload=chartc.convert(chart,meta,diff); out=outdir/f'{week}.{index}{suffix}.cht'; out.write_bytes(payload); records.append({'song':song,'variation':'erect','difficulty':diff,'file':out.name,'bytes':len(payload),'sha256':sha256(out)})
    a.manifest.parent.mkdir(parents=True,exist_ok=True); a.manifest.write_text(json.dumps({'count':len(records),'charts':records},indent=2)+'\n'); print(f'generated {len(records)} charts')
if __name__=='__main__': main()
