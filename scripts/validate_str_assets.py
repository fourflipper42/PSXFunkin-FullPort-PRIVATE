#!/usr/bin/env python3
"""Strict structural validation for every generated 2336-byte PSX STR asset."""
from __future__ import annotations

import argparse
import struct
from collections import defaultdict
from pathlib import Path

SECTOR = 2336
STR_MAGIC = 0x80010160


def validate(path: Path) -> tuple[int, int, int]:
    data = path.read_bytes()
    if not data or len(data) % SECTOR:
        raise SystemExit(f"{path}: not a non-empty 2336-byte sector stream")
    chunks: dict[int, set[int]] = defaultdict(set)
    totals: dict[int, int] = {}
    dimensions = set()
    audio_sectors = 0
    video_sectors = 0
    for offset in range(0, len(data), SECTOR):
        sector = data[offset:offset + SECTOR]
        index = offset // SECTOR
        if sector[:4] != sector[4:8]:
            raise SystemExit(f"{path}: XA subheader copy mismatch at sector {index}")
        submode = sector[2]
        if submode & 0x04:
            audio_sectors += 1
        if submode == 0x48:
            video_sectors += 1
            magic, chunk, total, frame = struct.unpack_from("<IHHI", sector, 8)
            if magic != STR_MAGIC:
                raise SystemExit(f"{path}: bad STR magic at sector {index}: {magic:#x}")
            width, height = struct.unpack_from("<HH", sector, 24)
            if not (0 < width <= 320 and 0 < height <= 240):
                raise SystemExit(f"{path}: unsafe frame dimensions {width}x{height}")
            if total == 0 or chunk >= total:
                raise SystemExit(f"{path}: invalid frame {frame} chunk {chunk}/{total}")
            if frame in totals and totals[frame] != total:
                raise SystemExit(f"{path}: frame {frame} changes chunk count")
            totals[frame] = total
            chunks[frame].add(chunk)
            dimensions.add((width, height))
    if not chunks:
        raise SystemExit(f"{path}: no video sectors")
    if audio_sectors == 0:
        raise SystemExit(f"{path}: no XA audio sectors")
    frame_ids = sorted(chunks)
    if frame_ids != list(range(frame_ids[0], frame_ids[-1] + 1)):
        raise SystemExit(f"{path}: non-contiguous frame numbers")
    for frame, seen in chunks.items():
        expected = set(range(totals[frame]))
        if seen != expected:
            raise SystemExit(f"{path}: incomplete frame {frame}: {sorted(seen)} / {totals[frame]}")
    if len(dimensions) != 1:
        raise SystemExit(f"{path}: dimensions change mid-stream: {sorted(dimensions)}")
    return len(frame_ids), video_sectors, audio_sectors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.paths:
        frames, video, audio = validate(path)
        print(f"STR_STRUCTURE_OK {path}: {frames} frames, {video} video sectors, {audio} audio sectors")


if __name__ == "__main__":
    main()
