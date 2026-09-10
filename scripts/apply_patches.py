#!/usr/bin/env python3
"""Apply the ordered patch series to the exact, clean supported upstream tree."""
import argparse
from pathlib import Path
import subprocess

UPSTREAM_REV = '850e0207479d8fb658bdc7637f6bfbc28a2b4066'
ROOT = Path(__file__).resolve().parents[1]

def apply(upstream):
    def git(*args):
        return subprocess.run(['git', '-C', str(upstream), *args], check=True,
                              text=True, capture_output=True).stdout.strip()
    if git('rev-parse', 'HEAD') != UPSTREAM_REV:
        raise ValueError(f'Expected upstream revision {UPSTREAM_REV}')
    if git('status', '--porcelain'):
        raise ValueError('Upstream must be clean before applying patches; use a fresh checkout.')
    patches = sorted((ROOT / 'patches').glob('*.patch'))
    if not patches:
        raise ValueError('No source patches found')
    # Later patches depend on earlier ones, so check and apply in order.
    # On failure the checkout retains earlier patches for diagnosis.
    for patch in patches:
        git('apply', '--check', str(patch))
        git('apply', str(patch))
    git('diff', '--check')
    print(f'Applied {len(patches)} patches to {UPSTREAM_REV}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream', type=Path)
    args = parser.parse_args()
    try:
        apply(args.upstream)
    except (ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(getattr(exc, 'stderr', None) or str(exc))
