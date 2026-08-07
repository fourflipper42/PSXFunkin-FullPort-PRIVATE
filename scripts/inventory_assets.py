#!/usr/bin/env python3
import hashlib, json, os, sys, zipfile
from collections import Counter, defaultdict

if len(sys.argv) != 3:
    raise SystemExit('usage: inventory_assets.py <zip-dir> <out-dir>')
zip_dir, out_dir = sys.argv[1:]
os.makedirs(out_dir, exist_ok=True)
report = {'archives': [], 'top_level_roots': Counter(), 'extensions': Counter(), 'files': []}
for name in sorted(os.listdir(zip_dir)):
    if not name.lower().endswith('.zip'):
        continue
    path = os.path.join(zip_dir, name)
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    arc = {'name': name, 'size': os.path.getsize(path), 'sha256': h.hexdigest(), 'entries': 0}
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            arc['entries'] += 1
            p = info.filename.replace('\\','/')
            root = p.split('/',1)[0]
            ext = os.path.splitext(p)[1].lower() or '<none>'
            report['top_level_roots'][root] += 1
            report['extensions'][ext] += 1
            report['files'].append({'archive': name, 'path': p, 'size': info.file_size})
    report['archives'].append(arc)
report['top_level_roots'] = dict(report['top_level_roots'].most_common())
report['extensions'] = dict(report['extensions'].most_common())
with open(os.path.join(out_dir, 'asset_inventory.json'), 'w') as f:
    json.dump(report, f, indent=2)
with open(os.path.join(out_dir, 'asset_inventory.txt'), 'w') as f:
    for a in report['archives']:
        f.write(f"{a['name']}\t{a['entries']} files\t{a['size']} bytes\t{a['sha256']}\n")
    f.write('\nTop-level roots:\n')
    for k,v in report['top_level_roots'].items(): f.write(f'{k}: {v}\n')
    f.write('\nExtensions:\n')
    for k,v in report['extensions'].items(): f.write(f'{k}: {v}\n')
