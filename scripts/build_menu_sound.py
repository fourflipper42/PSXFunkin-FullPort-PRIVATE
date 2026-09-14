#!/usr/bin/env python3
"""Encode pinned official menu SFX at 44.1 kHz into resident SPU banks."""
import argparse,json,struct,subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

def build(root,upstream,encoder,report):
    out=upstream/'iso/menu';out.mkdir(parents=True,exist_ok=True)
    xml=ET.parse(upstream/'funkin.xml');directory=xml.find(".//dir[@name='menu']")
    if directory is None:raise ValueError('Missing menu disc directory')
    records=[];address=0x1010
    for name in ('scroll','confirm','cancel'):
        path=out/f'{name}.vag'
        subprocess.run([str(encoder.resolve()),'-t','vag','-f','44100','-n',str(root/f'sounds/{name}Menu.ogg'),str(path)],check=True,capture_output=True)
        data=path.read_bytes();size,rate=struct.unpack_from('>II',data,12)
        if data[:4]!=b'VAGp' or rate!=44100 or size%16 or len(data)<size+48:raise ValueError('Invalid encoded VAG')
        if address+size>0x80000:raise ValueError('Menu sounds exceed retail SPU RAM')
        records.append(dict(name=name,spu_address=address,sample_rate=rate,adpcm_bytes=size))
        address=(address+size+63)&~63
        if directory.find(f"file[@name='{name}.vag']") is None:
            ET.SubElement(directory,'file',name=f'{name}.vag',type='data',source=f'iso/menu/{name}.vag')
    xml.write(upstream/'funkin.xml',encoding='utf-8',xml_declaration=True)
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(dict(sounds=records,spu_end=address,spu_limit=0x80000),indent=2)+'\n')
    print(report.read_text())

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','upstream','encoder','report'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();build(a.root,a.upstream,a.encoder,a.report)
