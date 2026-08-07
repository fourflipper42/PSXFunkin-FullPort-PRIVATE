#!/usr/bin/env python3
"""Build a quality-first Character Select live scene for PS1.

This deliberately stops trying to represent the live Character Select screen as
160x120 4bpp animation. The intro remains on the existing compact path, while
the live screen uses:
  * one native 320x240 16bpp static environment/background frame;
  * native 320x240 8bpp BF/GF + official foreground animation frames;
  * a small number of high-quality animation samples so the bank remains safe
    for 2 MiB PlayStation RAM while stayFunky streams from CD-XA.

All art is rendered from the already-loaded official v0.8.4 assets by the
existing Character Select builder. No replacement artwork is generated.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path

from PIL import Image

MAGIC = b"CSQ2"
W = 320
H = 240
CLUT_COLORS = 256
CLUT_BYTES = CLUT_COLORS * 2
PIXEL8_BYTES = W * H
RECORD8_BYTES = CLUT_BYTES + PIXEL8_BYTES

IDLE_COUNT = 4
LOCKED_COUNT = 2
CONFIRM_COUNT = 3
DENY_COUNT = 1
IDLE_FIRST = 0
LOCKED_FIRST = IDLE_FIRST + IDLE_COUNT
CONFIRM_FIRST = LOCKED_FIRST + LOCKED_COUNT
DENY_FIRST = CONFIRM_FIRST + CONFIRM_COUNT
FRAME_COUNT = DENY_FIRST + DENY_COUNT


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_builder(path: Path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("charselect_v4_source", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    # dataclasses resolves postponed annotations through sys.modules while the
    # module body is executing. Register the dynamic module before exec_module.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def encode_16bpp(image: Image.Image, psx_color) -> bytes:
    image = image.convert("RGBA")
    if image.size != (W, H):
        raise RuntimeError(f"16bpp frame size {image.size} != {(W, H)}")
    out = bytearray()
    for r, g, b, a in image.getdata():
        value = 0 if a < 128 else psx_color((r, g, b))
        out.extend(struct.pack("<H", value))
    if len(out) != W * H * 2:
        raise RuntimeError("16bpp background byte count mismatch")
    return bytes(out)


def quantize_8bpp(image: Image.Image, psx_color) -> bytes:
    image = image.convert("RGBA")
    if image.size != (W, H):
        raise RuntimeError(f"8bpp frame size {image.size} != {(W, H)}")

    alpha = image.getchannel("A")
    rgb = Image.new("RGB", image.size, (0, 0, 0))
    rgb.paste(image.convert("RGB"), mask=alpha)

    # 255 authored colours + index 0 reserved for transparency. No dithering:
    # Funkin's flat line art stays crisp instead of becoming a noisy pattern.
    q = rgb.quantize(
        colors=255,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    raw = q.getpalette()[:255 * 3]
    colors = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
    while len(colors) < 255:
        colors.append((0, 0, 0))

    palette = [0] + [psx_color(c) for c in colors[:255]]
    clut = b"".join(struct.pack("<H", c) for c in palette)

    qpix = list(q.getdata())
    apix = list(alpha.getdata())
    pixels = bytes(0 if a < 128 else int(idx) + 1 for idx, a in zip(qpix, apix))
    record = clut + pixels
    if len(record) != RECORD8_BYTES:
        raise RuntimeError(f"8bpp record {len(record)} != {RECORD8_BYTES}")
    return record


def packbits(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        run = 1
        while i + run < n and data[i + run] == data[i] and run < 130:
            run += 1
        if run >= 3:
            out.append(0x80 | (run - 3))
            out.append(data[i])
            i += run
            continue

        start = i
        i += run
        while i < n and i - start < 128:
            run = 1
            while i + run < n and data[i + run] == data[i] and run < 130:
                run += 1
            if run >= 3 or i - start + run > 128:
                break
            i += run
        literal = data[start:i]
        if not 1 <= len(literal) <= 128:
            raise RuntimeError(f"invalid literal length {len(literal)}")
        out.append(len(literal) - 1)
        out.extend(literal)
    return bytes(out)


def pack_csq2(records: list[bytes]) -> bytes:
    if not records:
        raise RuntimeError("no v4 character records")
    if any(len(r) != RECORD8_BYTES for r in records):
        raise RuntimeError("v4 record size mismatch")

    packed = [packbits(r) for r in records]
    header_size = 12 + len(records) * 8
    cursor = header_size
    entries = []
    payload = bytearray()
    for frame in packed:
        entries.append((cursor, len(frame)))
        payload.extend(frame)
        cursor += len(frame)

    blob = bytearray(struct.pack("<4sHHI", MAGIC, len(records), 0, RECORD8_BYTES))
    for offset, size in entries:
        blob.extend(struct.pack("<II", offset, size))
    blob.extend(payload)
    return bytes(blob)


def decode_csq2(blob: bytes) -> list[bytes]:
    magic, count, _reserved, record_bytes = struct.unpack_from("<4sHHI", blob, 0)
    if magic != MAGIC or record_bytes != RECORD8_BYTES:
        raise RuntimeError("bad CSQ2 header")
    result = []
    for frame in range(count):
        offset, packed_size = struct.unpack_from("<II", blob, 12 + frame * 8)
        src = memoryview(blob)[offset:offset + packed_size]
        out = bytearray()
        pos = 0
        while pos < len(src):
            control = src[pos]
            pos += 1
            if control & 0x80:
                length = (control & 0x7F) + 3
                if pos >= len(src):
                    raise RuntimeError("truncated CSQ2 run")
                value = src[pos]
                pos += 1
                out.extend([value] * length)
            else:
                length = (control & 0x7F) + 1
                if pos + length > len(src):
                    raise RuntimeError("truncated CSQ2 literal")
                out.extend(src[pos:pos + length])
                pos += length
        if len(out) != RECORD8_BYTES:
            raise RuntimeError(f"decoded v4 frame {frame}: {len(out)} != {RECORD8_BYTES}")
        result.append(bytes(out))
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--builder", type=Path, required=True,
                    help="already-patched build_v084_charselect_full.py used by this CI run")
    ap.add_argument("--assets-root", type=Path, required=True)
    ap.add_argument("--upstream", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    mod = load_builder(args.builder)
    # Reuse the proven official Animate reconstruction, but render at the actual
    # PS1 display resolution instead of the old 160x120/256x192 compromises.
    mod.SCENE_W = W
    mod.SCENE_H = H
    mod.CHAR_W = W
    mod.CHAR_H = H

    root = args.assets_root
    names = ["crowd", "charSelectStage", "barThing", "bfChill", "gfChill", "lockedChill", "charSelectSpeakers"]
    anims = {name: mod.load_optional_anim(root, name) for name in names}
    required = ["crowd", "charSelectStage", "bfChill", "lockedChill", "charSelectSpeakers"]
    missing = [name for name in required if anims[name] is None]
    if missing:
        raise SystemExit(f"v4 official Character Select Animate data missing: {missing}")

    menu_dir = args.upstream / "iso" / "menu"
    menu_dir.mkdir(parents=True, exist_ok=True)

    # One full-quality static live environment. The official foreground pieces
    # were already split out by parity v3, so they are not baked behind BF/GF.
    bg = mod.build_environment_scene(root, anims, 0, 1)
    bg16 = menu_dir / "csbg16.bin"
    bg16.write_bytes(encode_16bpp(bg, mod.base.psx_color))

    frames = (
        [mod.build_character_overlay(root, anims, "idle", i, IDLE_COUNT) for i in range(IDLE_COUNT)] +
        [mod.build_character_overlay(root, anims, "locked", i, LOCKED_COUNT) for i in range(LOCKED_COUNT)] +
        [mod.build_character_overlay(root, anims, "confirm", i, CONFIRM_COUNT) for i in range(CONFIRM_COUNT)] +
        [mod.build_character_overlay(root, anims, "deny", i, DENY_COUNT) for i in range(DENY_COUNT)]
    )
    records = [quantize_8bpp(frame, mod.base.psx_color) for frame in frames]
    if len(records) != FRAME_COUNT:
        raise RuntimeError(f"v4 character frame count {len(records)} != {FRAME_COUNT}")

    packed = pack_csq2(records)
    if decode_csq2(packed) != records:
        raise RuntimeError("v4 CSQ2 lossless round-trip failed")
    char8 = menu_dir / "cschar8.rle"
    char8.write_bytes(packed)

    # The old >700 KiB contiguous allocation was already proven unsafe on PS1.
    # Keep this bank comfortably below that while retaining native-resolution
    # 8bpp frames. If a future asset change breaks the budget, fail CI instead
    # of silently reintroducing a crash-prone build.
    if char8.stat().st_size >= 600000:
        raise RuntimeError(f"v4 character bank too large for safe menu RAM budget: {char8.stat().st_size}")

    report = json.loads(args.report.read_text()) if args.report.is_file() else {}
    report["character_select_quality_v4"] = {
        "policy": "quality-first native PS1 presentation from official v0.8.4 assets",
        "live_background": {
            "file": "csbg16.bin",
            "size": [W, H],
            "format": "PS1 16bpp direct colour",
            "bytes": bg16.stat().st_size,
            "sha256": sha256(bg16),
            "animation": "static live environment; quality prioritized over background motion",
        },
        "character_foreground": {
            "file": "cschar8.rle",
            "size": [W, H],
            "format": "PS1 8bpp, per-frame 256-entry CLUT, index 0 transparent",
            "frame_count": FRAME_COUNT,
            "record_bytes": RECORD8_BYTES,
            "packed_bytes": char8.stat().st_size,
            "sha256": sha256(char8),
            "ranges": {
                "idle": [IDLE_FIRST, IDLE_COUNT],
                "locked": [LOCKED_FIRST, LOCKED_COUNT],
                "confirm": [CONFIRM_FIRST, CONFIRM_COUNT],
                "deny": [DENY_FIRST, DENY_COUNT],
            },
        },
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n")

    print(f"v4 live background: 320x240 16bpp, {bg16.stat().st_size} bytes")
    print(f"v4 character/foreground: {FRAME_COUNT} native 320x240 8bpp frames")
    print(f"v4 raw character bytes: {FRAME_COUNT * RECORD8_BYTES}")
    print(f"v4 packed character bytes: {char8.stat().st_size}")
    print(f"v4 compression: {char8.stat().st_size * 100.0 / (FRAME_COUNT * RECORD8_BYTES):.1f}%")
    print("v4 quality target: no 160x120 live background, no 4bpp live character layer")


if __name__ == "__main__":
    main()
