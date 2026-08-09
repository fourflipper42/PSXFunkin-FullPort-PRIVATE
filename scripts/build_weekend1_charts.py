#!/usr/bin/env python3
from __future__ import annotations
import argparse, importlib.util, json, sys
from pathlib import Path

KIND_CODES={
 'weekend-1-lightcan':1, 'weekend-1-kickcan':2, 'weekend-1-cockgun':3,
 'weekend-1-kneecan':4, 'weekend-1-firegun':5,
 'weekend-1-blockhigh':10, 'weekend-1-punchhighblocked':11,
 'weekend-1-punchlowdodged':12, 'weekend-1-dodgelow':13,
 'weekend-1-blockspin':14, 'weekend-1-punchhigh':15,
 'weekend-1-hithigh':16, 'weekend-1-dodgehigh':17,
 'weekend-1-darnelluppercutprep':18, 'weekend-1-darnelluppercut':19,
 'weekend-1-hitlow':20, 'weekend-1-picouppercutprep':21,
 'weekend-1-picouppercut':22, 'weekend-1-blocklow':23,
 'weekend-1-punchlow':24, 'weekend-1-punchlowspin':25,
 'weekend-1-fakeout':26, 'weekend-1-taunt':27,
 'weekend-1-idle':28, 'weekend-1-punchlowblocked':29,
 'weekend-1-punchhighspin':30,
}
SONGS=[('darnell',1),('lit-up',2),('2hot',3),('blazin',4)]
BASE=(('easy','e'),('normal','n'),('hard','h'))
EXTRA=(('erect','r'),('nightmare','m'))

def load_chartc():
 p=Path(__file__).with_name('psxfunkin_chartc_weekend1.py'); spec=importlib.util.spec_from_file_location('chartc',p); m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m); return m

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); ap.add_argument('--iso-root',type=Path,required=True); ap.add_argument('--report',type=Path,required=True); a=ap.parse_args(); c=load_chartc(); rec=[]
 out=a.iso_root/'chart'; out.mkdir(parents=True,exist_ok=True)
 for song,idx in SONGS:
  sd=a.root/'data/songs'/song; chart=json.loads((sd/f'{song}-chart.json').read_text()); meta=json.loads((sd/f'{song}-metadata.json').read_text())
  for diff,suf in BASE:
   payload=c.convert(chart,meta,diff,kind_codes=KIND_CODES); p=out/f'8.{idx}{suf}.cht'; p.write_bytes(payload); rec.append({'song':song,'difficulty':diff,'file':p.name,'bytes':len(payload)})
  ep=sd/f'{song}-chart-erect.json'; em=sd/f'{song}-metadata-erect.json'
  if ep.exists() and em.exists():
   ec=json.loads(ep.read_text()); emd=json.loads(em.read_text())
   for diff,suf in EXTRA:
    if diff in ec.get('notes',{}):
     payload=c.convert(ec,emd,diff,kind_codes=KIND_CODES); p=out/f'8.{idx}{suf}.cht'; p.write_bytes(payload); rec.append({'song':song,'difficulty':diff,'file':p.name,'bytes':len(payload)})
 a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps({'kind_codes':KIND_CODES,'charts':rec},indent=2)+'\n'); print(f'generated {len(rec)} Weekend 1 charts')
if __name__=='__main__': main()
