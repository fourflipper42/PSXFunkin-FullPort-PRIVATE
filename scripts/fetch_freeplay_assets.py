#!/usr/bin/env python3
"""Fetch pinned v0.8.4 BF Freeplay artwork for the PS1 adaptation."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import urllib.request
from fetch_menu_assets import BASE

def fetch(root):
    paths=['fonts/5by7.ttf','preload/data/players/bf.json','preload/data/ui/freeplay/styles/bf.json']
    images=['freeplay/pinkBack.png','freeplay/freeplayBGweek1-bf.png','freeplay/ref.png',
            'freeplay/freeplayeasy.png','freeplay/freeplaynormal.png','freeplay/freeplayhard.png',
            'freeplay/freeplayerect.png','freeplay/freeplaynightmare.png','freeplay/freeplaynightmare.xml']
    for name in ('freeplay-boyfriend',):
        images += [f'freeplay/{name}/{part}' for part in ('Animation.json','spritemap1.json','spritemap1.png')]
    for name in ('freeplayCapsule/capsule/freeplayCapsule','freeplaySelector/freeplaySelector'):
        images += [f'freeplay/{name}.{ext}' for ext in ('png','xml')]
    for name in ('bf','dad','spooky','monster','pico','mom','parents-christmas','senpai','spirit','tankman','darnell'):
        images += [f'freeplay/icons/{name}pixel.{ext}' for ext in ('png','xml')]
    paths += ['preload/images/'+p for p in images]
    def download(source):
        target=root/source.removeprefix('preload/')
        if target.exists():return
        target.parent.mkdir(parents=True,exist_ok=True)
        with urllib.request.urlopen(BASE+source,timeout=60) as response:data=response.read()
        target.write_bytes(data)
    with ThreadPoolExecutor(max_workers=4) as executor:list(executor.map(download,paths))
    print(f'{len(paths)} pinned Freeplay inputs available in {root}')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path)
    fetch(p.parse_args().root)
