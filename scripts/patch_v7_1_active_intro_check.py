#!/usr/bin/env python3
"""Replace the over-broad v7.1 intro validation with an active-path check."""
from pathlib import Path

p = Path('scripts/apply_charselect_v7_1_cleanup.py')
s = p.read_text()
old = "if 'csanim.rle;1' in low: raise SystemExit('old low-resolution intro still active')"
new = "if 'menu_cs_frames = io_read(\"\\\\\\\\menu\\\\\\\\csintro71.rle;1\");' not in low: raise SystemExit('native v7.1 intro bank is not the active Character Select intro')"
if s.count(old) != 1:
    raise SystemExit(f'active-intro validation anchor count {s.count(old)}')
p.write_text(s.replace(old, new, 1))
print('Replaced stale-literal rejection with exact active CSINTRO71 assignment validation.')
