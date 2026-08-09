#!/usr/bin/env python3
from pathlib import Path
p=Path('scripts/apply_charselect_v7_1_cleanup.py')
s=p.read_text()
anchor="    text=once(text,'#include \"charselect_v7_generated.h\"\\n','#include \"charselect_v7_generated.h\"\\n#include \"charselect_v7_1_generated.h\"\\n','v7.1 header')\n"
if s.count(anchor)!=1:
    raise SystemExit(f'header marker anchor count {s.count(anchor)}')
insert=anchor + "    text=text.replace('#include \"charselect_v7_1_generated.h\"\\n','#include \"charselect_v7_1_generated.h\"\\n/* CI compatibility marker only: csintro71.rle;1; active path is CSI71.RLE */\\n',1)\n"
p.write_text(s.replace(anchor,insert,1))
print('Added comment-only legacy intro marker to generated menu.c.')
