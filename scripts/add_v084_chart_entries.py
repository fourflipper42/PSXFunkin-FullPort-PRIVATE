#!/usr/bin/env python3
from pathlib import Path
import argparse,re
EXTRA=[(1,1),(1,2),(1,3),(2,1),(2,2),(3,1),(3,2),(3,3),(4,1),(4,2),(5,1),(5,2),(6,1),(6,2),(6,3),(7,1)]
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('xml',type=Path); a=ap.parse_args(); text=a.xml.read_text()
    for week,song in EXTRA:
        if f'name = "{week}.{song}r.cht"' in text: continue
        pat=re.compile(r'(?P<indent>\s*)<file name = "'+re.escape(f'{week}.{song}h.cht')+r'" type = "data" source = "iso/chart/'+re.escape(f'{week}.{song}h.cht')+r'"/>'); m=pat.search(text)
        if not m: raise SystemExit(f'could not locate hard chart XML entry for {week}.{song}')
        indent=m.group('indent'); base=m.group(0)
        addition=base+f'{indent}<file name = "{week}.{song}r.cht" type = "data" source = "iso/chart/{week}.{song}r.cht"/>'+f'{indent}<file name = "{week}.{song}m.cht" type = "data" source = "iso/chart/{week}.{song}m.cht"/>'
        text=text[:m.start()]+addition+text[m.end():]
    a.xml.write_text(text); print(f'added Erect/Nightmare XML entries for {len(EXTRA)} songs')
if __name__=='__main__': main()
