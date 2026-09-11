#!/usr/bin/env python3
"""Remove the upstream license-file placeholder from the homebrew disc manifest."""
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET

def prepare(path: Path):
    tree=ET.parse(path)
    for track in tree.findall('.//track'):
        for license in list(track.findall('license')):
            if license.get('file') == 'licensea.dat':
                track.remove(license)
    tree.write(path,encoding='utf-8',xml_declaration=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    prepare(parser.parse_args().manifest)
