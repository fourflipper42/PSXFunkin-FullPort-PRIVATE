#!/usr/bin/env python3
from __future__ import annotations
import struct
from pathlib import Path


def pack_arc(output: Path, files: list[Path], names: list[str] | None = None) -> None:
    if not 1 <= len(files) <= 16:
        raise ValueError('PSXFunkin ARC supports 1..16 files')
    if names is None:
        names=[p.name for p in files]
    if len(names)!=len(files): raise ValueError('name/file count mismatch')
    for n in names:
        if len(n.encode('ascii')) > 12: raise ValueError(f'ARC member name too long: {n}')
    header=bytearray(16*16)
    pos=len(header); payload=bytearray()
    entries=[]
    for p,n in zip(files,names):
        data=p.read_bytes(); pos=(pos+15)&~15
        while len(header)+len(payload)<pos: payload += b'\0'
        entries.append((n,pos))
        payload += data
        pos += len(data)
    for i,(n,off) in enumerate(entries):
        nb=n.encode('ascii').ljust(12,b'\0')
        header[i*16:i*16+12]=nb
        struct.pack_into('<I',header,i*16+12,off)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(header+payload)
