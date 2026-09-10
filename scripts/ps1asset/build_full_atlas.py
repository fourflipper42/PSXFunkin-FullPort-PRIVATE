#!/usr/bin/env python3
"""Render every labeled source frame at an explicit scale into a verified FBK1 bank."""
import argparse
import json
import math
from pathlib import Path
from animateatlas_flatten import AnimateAtlas, leaf_bounds, render_leaves_fixed
from framebank import encode_images


def build(atlas_dir, output, scale=0.22):
    atlas = AnimateAtlas(atlas_dir)
    labels = atlas.labels()
    if not labels: raise ValueError('atlas has no labeled animations')
    source_frames = sorted({i for label in labels for i in range(label['start'], label['start']+label['duration'])})
    leaves = {i: atlas.leaves_for_frame(i) for i in source_frames}
    bounds = [leaf_bounds(leaf) for values in leaves.values() for leaf in values]
    if not bounds: raise ValueError('atlas has no drawable frames')
    min_x, min_y = min(b[0] for b in bounds), min(b[1] for b in bounds)
    max_x, max_y = max(b[2] for b in bounds), max(b[3] for b in bounds)
    width = (math.ceil((max_x-min_x)*scale)+9) & ~1
    height = math.ceil((max_y-min_y)*scale)+8
    if width > 256 or height > 256:
        raise ValueError(f'{atlas_dir}: {width}x{height} needs tiled rendering at scale {scale}; refusing to shrink silently')
    transform = (scale, 0, 0, scale, 4-min_x*scale, 4-min_y*scale)
    images = [render_leaves_fixed(leaves[i], (width, height), transform) for i in source_frames]
    data, report = encode_images(images)
    lookup = {source: i for i, source in enumerate(source_frames)}
    report.update({'source': str(atlas_dir), 'scale': scale, 'frame_rate': atlas.frame_rate,
                   'world_bounds': [min_x,min_y,max_x,max_y],
                   'origin': [4-min_x*scale,4-min_y*scale],
                   'animations': {label['name']: [lookup[i] for i in range(label['start'], label['start']+label['duration'])] for label in labels}})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('atlas',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--scale',type=float,default=0.22)
    a=p.parse_args();r=build(a.atlas,a.output,a.scale)
    print(json.dumps({k:v for k,v in r.items() if k!='animations'},indent=2))
