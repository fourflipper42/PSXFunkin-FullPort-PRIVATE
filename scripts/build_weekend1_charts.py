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

EASE_INSTANT=0
EASE_QUAD=1
EASE_ELASTIC=2

def load_chartc():
 p=Path(__file__).with_name('psxfunkin_chartc_weekend1.py'); spec=importlib.util.spec_from_file_location('chartc',p); m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m); return m

def ease_code(value):
 s=str(value or '').lower()
 if 'elastic' in s: return EASE_ELASTIC
 if 'quad' in s or 'sine' in s or 'classic' in s: return EASE_QUAD
 return EASE_INSTANT

def event_tables(chart,meta,chartc):
 changes=chartc.read_time_changes(meta); focus=[]; zoom=[]
 for event in chart.get('events',[]):
  step=chartc.round_half_up(chartc.time_to_beat(float(event.get('t',0)),changes)*4.0)
  value=event.get('v') or {}
  if event.get('e')=='FocusCamera':
   char=chartc.normalize_focus_value(value)
   if isinstance(value,dict) and value.get('char')==2: char=2
   if char in (0,1,2):
    # Stage artwork is rendered at 22% of the original coordinate system.
    focus.append((step,char,round(float(value.get('x',0))*0.22),round(float(value.get('y',0))*0.22)))
  elif event.get('e')=='ZoomCamera' and isinstance(value,dict) and 'zoom' in value:
   duration=chartc.round_half_up(float(value.get('duration',0))*4.0)
   zoom.append((step,duration,round(float(value['zoom'])*1024),ease_code(value.get('ease'))))
 return focus,zoom

def c_table(name,ctype,rows):
 if not rows: return f'static const {ctype} {name}[] = {{{{0}}}};\n#define {name.upper()}_COUNT 0\n'
 vals=',\n'.join('    {'+', '.join(str(v) for v in row)+'}' for row in rows)
 return f'static const {ctype} {name}[] = {{\n{vals}\n}};\n#define {name.upper()}_COUNT {len(rows)}\n'

def write_event_header(path, tables):
 out=['#ifndef _WEEKEND1_EVENTS_GENERATED_H','#define _WEEKEND1_EVENTS_GENERATED_H','']
 for name,focus,zoom in tables:
  out.append(c_table(f'w1_focus_{name}','Weekend1FocusEvent',focus))
  out.append(c_table(f'w1_zoom_{name}','Weekend1ZoomEvent',zoom))
 out.append('#endif')
 path.parent.mkdir(parents=True,exist_ok=True); path.write_text('\n'.join(out)+'\n')

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); ap.add_argument('--iso-root',type=Path,required=True); ap.add_argument('--report',type=Path,required=True); ap.add_argument('--header',type=Path,required=True); a=ap.parse_args(); c=load_chartc(); rec=[]; tables=[]
 out=a.iso_root/'chart'; out.mkdir(parents=True,exist_ok=True)
 for song,idx in SONGS:
  sd=a.root/'data/songs'/song; chart=json.loads((sd/f'{song}-chart.json').read_text()); meta=json.loads((sd/f'{song}-metadata.json').read_text())
  focus,zoom=event_tables(chart,meta,c); tables.append((str(idx),focus,zoom))
  for diff,suf in BASE:
   payload=c.convert(chart,meta,diff,kind_codes=KIND_CODES); p=out/f'8.{idx}{suf}.cht'; p.write_bytes(payload); rec.append({'song':song,'difficulty':diff,'file':p.name,'bytes':len(payload)})
  ep=sd/f'{song}-chart-erect.json'; em=sd/f'{song}-metadata-erect.json'
  if ep.exists() and em.exists():
   ec=json.loads(ep.read_text()); emd=json.loads(em.read_text())
   focus,zoom=event_tables(ec,emd,c); tables.append((f'{idx}_erect',focus,zoom))
   for diff,suf in EXTRA:
    if diff in ec.get('notes',{}):
     payload=c.convert(ec,emd,diff,kind_codes=KIND_CODES); p=out/f'8.{idx}{suf}.cht'; p.write_bytes(payload); rec.append({'song':song,'difficulty':diff,'file':p.name,'bytes':len(payload)})
 write_event_header(a.header,tables)
 a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps({'kind_codes':KIND_CODES,'charts':rec,'event_tables':[{'name':n,'focus':len(f),'zoom':len(z)} for n,f,z in tables]},indent=2)+'\n'); print(f'generated {len(rec)} Weekend 1 charts and {len(tables)} event tables')
if __name__=='__main__': main()
