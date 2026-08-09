#!/usr/bin/env python3
from pathlib import Path
p=Path('scripts/build_charselect_v7_1_cleanup.py')
s=p.read_text()
repls={
    "(menu/f'cslock71{chr(97+i)}.tim').write_bytes(data)":"(menu/f'csl71{chr(97+i)}.tim').write_bytes(data)",
    "(menu/f'csctrl71{chr(97+i)}.tim').write_bytes(data)":"(menu/f'csc71{chr(97+i)}.tim').write_bytes(data)",
}
for old,new in repls.items():
    if s.count(old)!=1: raise SystemExit(f'expected one dynamic filename anchor: {old}')
    s=s.replace(old,new,1)
p.write_text(s)
print('Corrected dynamic v7.1 TIM outputs to 8.3-safe names.')
