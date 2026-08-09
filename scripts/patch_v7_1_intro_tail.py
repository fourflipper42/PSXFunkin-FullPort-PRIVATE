#!/usr/bin/env python3
"""Keep v7.1 intro sampling away from the unreliable decoder EOF boundary."""
from pathlib import Path

p=Path('scripts/build_charselect_v7_1_cleanup.py')
s=p.read_text()
old="""            t = duration * i / max(1, INTRO_COUNT-1)\n            if i == INTRO_COUNT-1: t=max(0.0,duration-0.03)\n"""
new="""            # Sample uniformly inside the movie rather than exactly at/near EOF.\n            # Some v0.8.4 introSelect encodes do not return a decoded frame in the\n            # final few tens of milliseconds. 23/24 still captures the visual tail.\n            t = duration * i / INTRO_COUNT\n"""
if s.count(old)!=1:
    raise SystemExit(f'intro-tail anchor count {s.count(old)}')
p.write_text(s.replace(old,new,1))
print('Moved v7.1 final intro sample safely inside the official movie duration.')
