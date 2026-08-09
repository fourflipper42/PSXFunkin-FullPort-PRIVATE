#!/usr/bin/env python3
"""Launch build_charselect_source_v7 with the direct Sparrow helper it expects.

The v6 module imports atlas helpers but does not itself expose the builder's
`sparrow_frame` method. Keep this adapter isolated instead of modifying the
working v5/v6 conversion modules.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import build_charselect_source_v7 as v7


def direct_sparrow_frame(png: Path, xml: Path, i: int, count: int):
    nodes = list(ET.parse(xml).getroot())
    if not nodes:
        raise RuntimeError(f'empty Sparrow atlas: {xml}')
    # For one-shot selector confirmation/denial art, sample across the authored
    # XML frame sequence using the same normalized i/count convention as the
    # original Character Select builder.
    index = min(len(nodes) - 1, max(0, (i * len(nodes)) // max(1, count)))
    return v7.reconstruct_sparrow_frame(png, nodes[index])


v7.v6.sparrow_frame = direct_sparrow_frame

if __name__ == '__main__':
    v7.main()
