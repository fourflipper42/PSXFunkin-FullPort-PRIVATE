#!/usr/bin/env python3
"""Check the linked PS1 image against retail RAM, including a movie stack reserve."""
import argparse,json,struct
from pathlib import Path
RAM_START=0x80010000
RAM_END=0x80200000
# Current 320x240 STR local arrays use 388,096 bytes. Reserve another
# 136,192 bytes for callees, interrupts, alignment and ordinary stack use.
STACK_RESERVE=512*1024

def validate(executable:Path,symbols:Path):
    data=executable.read_bytes()
    if len(data)<2048 or data[:8]!=b'PS-X EXE':raise ValueError('Invalid PS-X EXE header')
    entry=struct.unpack_from('<I',data,16)[0]
    address,size=struct.unpack_from('<II',data,24)
    sp,offset=struct.unpack_from('<II',data,48)
    sp+=offset
    if not size or len(data)!=2048+size or size%2048:raise ValueError('Invalid executable payload size')
    if not RAM_START<=address<=entry<address+size<=RAM_END:raise ValueError('Executable lies outside retail RAM')
    values={}
    for line in symbols.read_text().splitlines():
        parts=line.split()
        if len(parts)==3:
            try:values[parts[2]]=int(parts[0],16)
            except ValueError:pass
    if '__bss_end' not in values:raise ValueError('Missing BSS-end symbol; cannot account for static memory')
    end=max(address+size,values['__bss_end'])
    if not end<=sp<RAM_END:raise ValueError('Static image overlaps stack or exceeds RAM')
    available=sp-end
    if available<STACK_RESERVE:raise ValueError(f'Only {available} bytes remain for stack; need {STACK_RESERVE}')
    return {'ram_bytes':2*1024*1024,'load_address':hex(address),'static_end':hex(end),'stack_pointer':hex(sp),'available_stack_bytes':available,'reserved_stack_bytes':STACK_RESERVE,'stack_margin_bytes':available-STACK_RESERVE,'movie_local_array_bytes':388096,'dynamic_heap_peak_measured':False,'hardware_tested':False}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('executable',type=Path);p.add_argument('symbols',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
    result=validate(a.executable,a.symbols);text=json.dumps(result,indent=2)+'\n'
    if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(text)
    print(text,end='')
