#!/usr/bin/env python3
"""Validate single-track raw BIN/CUE size and references; this is not a boot test."""
import argparse
import json
from pathlib import Path
import re

RAW_SECTOR = 2352
# Conservative 74-minute target; allows a single standard CD without overburn.
DEFAULT_MAX_SECTORS = 74 * 60 * 75

def validate(bin_path, cue_path, max_sectors=DEFAULT_MAX_SECTORS):
    size = bin_path.stat().st_size
    if not size or size % RAW_SECTOR:
        raise ValueError('BIN must contain complete 2352-byte sectors')
    sectors = size // RAW_SECTOR
    if max_sectors <= 0 or sectors > max_sectors:
        raise ValueError(f'Disc uses {sectors} sectors; budget is {max_sectors}')
    cue = cue_path.read_text()
    files = re.findall(r'^\s*FILE\s+"([^"]+)"\s+BINARY\s*$', cue, re.M | re.I)
    tracks = re.findall(r'^\s*TRACK\s+(\d+)\s+(\S+)\s*$', cue, re.M | re.I)
    indices = re.findall(r'^\s*INDEX\s+(\d+)\s+(\S+)\s*$', cue, re.M | re.I)
    if len(files) != 1 or (cue_path.parent / files[0]).resolve() != bin_path.resolve():
        raise ValueError('CUE must reference exactly the supplied BIN')
    if tracks != [('01', 'MODE2/2352')] or indices != [('01', '00:00:00')]:
        raise ValueError('Expected one MODE2/2352 track starting at sector zero')
    return {'bytes': size, 'raw_sectors': sectors, 'max_sectors': max_sectors,
            'remaining_sectors': max_sectors - sectors,
            'hardware_tested': False}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bin', type=Path)
    parser.add_argument('cue', type=Path)
    parser.add_argument('--max-sectors', type=int, default=DEFAULT_MAX_SECTORS)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.bin, args.cue, args.max_sectors)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    text = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, end='')
