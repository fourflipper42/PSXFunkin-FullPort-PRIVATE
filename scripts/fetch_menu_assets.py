#!/usr/bin/env python3
"""Fetch the pinned official title/main-menu inputs for conversion and review."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import urllib.request

REV = 'd1d027d4747aaba151c6df121ea736c31d6aed38'
BASE = f'https://raw.githubusercontent.com/FunkinCrew/Funkin.assets/{REV}/'


def fetch(root):
    paths = ['fonts/vcr.ttf', 'exclude/data/credits.json', 'preload/data/introText.txt',
             'preload/images/menuBG.png', 'preload/images/menuBGMagenta.png']
    for name in ('mainmenu/storymode', 'mainmenu/freeplay', 'mainmenu/merch',
                 'mainmenu/options', 'mainmenu/credits', 'logoBumpin', 'gfDanceTitle'):
        paths += [f'preload/images/{name}.{extension}' for extension in ('png', 'xml')]
    paths += [f'preload/images/title-screen-text/{name}'
              for name in ('Animation.json', 'spritemap1.json', 'spritemap1.png')]
    paths += [f'preload/sounds/{name}.ogg' for name in ('scrollMenu', 'confirmMenu', 'cancelMenu')]
    def download(source):
        target = root / source.removeprefix('preload/')
        if target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(BASE + source, timeout=45) as response:
            data = response.read()
        target.write_bytes(data)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(download, paths))
    print(f'{len(paths)} pinned menu inputs available in {root}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    fetch(parser.parse_args().root)
