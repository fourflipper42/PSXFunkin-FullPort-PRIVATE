#!/usr/bin/env python3
"""Uppercase an ISO staging tree for predictable PS2 libcdvd lookup."""

from __future__ import annotations

import argparse
from pathlib import Path


def rename_children(directory: Path) -> None:
    children = sorted(directory.iterdir(), key=lambda p: len(p.parts), reverse=True)
    for child in children:
        if child.is_dir():
            rename_children(child)
        upper = child.with_name(child.name.upper())
        if upper == child:
            continue
        if upper.exists():
            raise RuntimeError(f"case collision: {child} -> {upper}")
        child.rename(upper)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")
    rename_children(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
