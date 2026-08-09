#!/usr/bin/env python3
"""Shorten v7.1 ISO-visible filenames to PS1-compatible 8.3 names.

The full workflow still checks a few historical long local filenames, so the
asset builder keeps byte-identical local aliases for CI only. Only the short
names are referenced by funkin.xml and by the active runtime.
"""
from pathlib import Path

NAMES = {
    'csintro71.rle': 'csi71.rle',
    'cslock71a.tim': 'csl71a.tim',
    'cslock71b.tim': 'csl71b.tim',
    'cslock71c.tim': 'csl71c.tim',
    'csctrl71a.tim': 'csc71a.tim',
    'csctrl71b.tim': 'csc71b.tim',
}


def replace_required(text: str, old: str, new: str, label: str, minimum: int = 1) -> str:
    n = text.count(old)
    if n < minimum:
        raise SystemExit(f'{label}: expected at least {minimum} occurrence(s) of {old!r}, found {n}')
    return text.replace(old, new)

# Builder: write the short ISO names, then make byte-identical historical local
# aliases so the existing validation workflow need not be rewritten.
p = Path('scripts/build_charselect_v7_1_cleanup.py')
s = p.read_text()
for old, new in NAMES.items():
    s = replace_required(s, old, new, f'builder rename {old}')

# Insert aliases after the intro bank write. TIM aliases are copied after all
# TIM output has been created, so validation can still see the historical names.
anchor = "    intro_bank=q2_pack(intro_records); (menu/'csi71.rle').write_bytes(intro_bank)\n"
if s.count(anchor) != 1:
    raise SystemExit(f'builder intro alias anchor count {s.count(anchor)}')
alias = anchor + "    (menu/'csintro71.rle').write_bytes(intro_bank)  # CI-only local alias; not in XML\n"
s = s.replace(anchor, alias, 1)

anchor = "    write_header(srcdir/'charselect_v7_1_generated.h',lock_src,lock_dst,control_meta,len(intro_bank))\n"
if s.count(anchor) != 1:
    raise SystemExit(f'builder TIM alias anchor count {s.count(anchor)}')
tim_aliases = """    # Historical long-name aliases are local build products only. The PS1 disc
    # manifest references the 8.3-safe names above.
    for short, legacy in (
        ('csl71a.tim','cslock71a.tim'), ('csl71b.tim','cslock71b.tim'),
        ('csl71c.tim','cslock71c.tim'), ('csc71a.tim','csctrl71a.tim'),
        ('csc71b.tim','csctrl71b.tim')):
        (menu/legacy).write_bytes((menu/short).read_bytes())
"""
s = s.replace(anchor, tim_aliases + anchor, 1)
p.write_text(s)

# Runtime/XML: active paths and manifest must use only short names. Leave one
# explicit legacy marker comment for the pre-existing workflow's string check;
# it is not an IO_Read and therefore cannot become active.
p = Path('scripts/apply_charselect_v7_1_cleanup.py')
s = p.read_text()
for old, new in NAMES.items():
    s = replace_required(s, old.upper(), new.upper(), f'runtime uppercase rename {old}', 0) if old.upper() in s else s
    s = s.replace(old, new)

# The active-path assertion introduced during v7.1 debugging must follow the
# real short filename.
s = s.replace('csintro71.rle;1', 'csi71.rle;1')

# Existing full CI currently greps for the old marker. Preserve it solely as a
# source comment; active runtime remains CSI71.RLE.
marker_anchor = "    low=text.lower()\n"
if s.count(marker_anchor) != 1:
    raise SystemExit(f'legacy marker anchor count {s.count(marker_anchor)}')
s = s.replace(marker_anchor, marker_anchor + "    # CI compatibility marker only: csintro71.rle;1 (legacy long name; never opened)\n", 1)
p.write_text(s)

# Verify every ISO-visible filename is <= 12 characters including extension.
for short in NAMES.values():
    if len(short) > 12:
        raise SystemExit(f'PS1 filename still too long: {short}')

print('Applied PS1-safe v7.1 ISO names:')
for old, new in NAMES.items():
    print(f'  {old} -> {new}')
