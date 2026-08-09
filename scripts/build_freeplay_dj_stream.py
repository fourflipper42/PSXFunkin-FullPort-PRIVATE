#!/usr/bin/env python3
"""Build a smooth PS1 stream from all official v0.8.4 Boyfriend DJ frames.

The official Animate symbol is flattened at build time only. All fourteen real
frames share one 4bpp palette and are stored in a tiny RAM-resident frame bank.
The first frame is also written into fpchar.tim so the existing Freeplay VRAM
slot and Gfx_Tex metadata remain unchanged.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import zipfile
from pathlib import Path, PurePosixPath

from PIL import Image

import build_v084_menu_visual_assets as base
import replace_freeplay_bf_with_official_dj as dj


def _github_actions_excepthook(exc_type, exc, tb):
    """Surface imported Pico asset failures through check annotations."""
    print(
        f"::error title=Pico asset builder failure::{exc_type.__name__}: {exc}",
        file=sys.stderr,
        flush=True,
    )
    sys.__excepthook__(exc_type, exc, tb)


# build_pico_mix_assets imports this module before doing any conversion work.
# Raw Actions logs for the private workflow are currently unavailable through
# the connector, so make any uncaught Python exception visible in the check's
# annotation API without changing build behavior.
sys.excepthook = _github_actions_excepthook

FRAME_W = 96
FRAME_H = 96
FRAME_COUNT = 14

# The split assets-v084 archives predate several Pico menu/Character Select
# files even though they are shipped in the SHA-pinned official v0.8.4 Linux
# release used by CI. Recover only those exact official bytes before the Pico
# builder imports/uses them; never synthesize or substitute artwork.
PICO_RELEASE_TREES = (
    "assets/images/freeplay/freeplay-pico",
    "assets/images/charSelect/picoChill",
    "assets/images/charSelect/neneChill",
)
PICO_RELEASE_FILES = (
    "assets/images/freeplay/freeplayBGweek1-pico.png",
    "assets/images/freeplay/freeplayCapsule/capsule/freeplayCapsule_pico.png",
    "assets/images/freeplay/freeplayCapsule/capsule/freeplayCapsule_pico.xml",
    "assets/images/freeplay/freeplaySelector/freeplaySelector_pico.png",
    "assets/images/freeplay/freeplaySelector/freeplaySelector_pico.xml",
    "assets/images/freeplay/icons/picopixel.png",
    "assets/images/freeplay/icons/picopixel.xml",
    "assets/images/charSelect/picoNametag.png",
    "assets/shared/images/characters/spooky_dark.png",
    "assets/shared/images/characters/spooky_dark.xml",
)


def recover_official_pico_sources() -> list[str]:
    """Recover missing Pico UI/character sources from the pinned v0.8.4 ZIP.

    Official release ZIPs may wrap ``assets/`` in a top-level directory. Match
    canonical v0.8.4 paths by case-insensitive suffix, like the proven Weekend
    recovery path, while still requiring the exact canonical asset subtree.
    """
    workspace = Path.cwd()
    root = workspace / "official-v084"
    archive = workspace / "official-assets/funkin-linux-64bit.zip"
    if not root.is_dir() or not archive.is_file():
        return []

    recovered: list[str] = []
    with zipfile.ZipFile(archive) as zf:
        files = [
            info
            for info in zf.infolist()
            if not info.is_dir()
        ]

        def best_file_match(source: str) -> zipfile.ZipInfo | None:
            canonical = source.lower().strip("/")
            matches = [
                info for info in files
                if info.filename.lower().strip("/") == canonical
                or info.filename.lower().strip("/").endswith("/" + canonical)
            ]
            if not matches:
                return None
            return sorted(
                matches,
                key=lambda info: (
                    len(PurePosixPath(info.filename).parts),
                    len(info.filename),
                    info.filename.lower(),
                ),
            )[0]

        def tree_matches(source: str) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
            canonical = source.lower().strip("/")
            prefix = canonical + "/"
            wrapped = "/" + prefix
            matches: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
            for info in files:
                low = info.filename.lower().strip("/")
                if low.startswith(prefix):
                    offset = len(prefix)
                    raw = info.filename.strip("/")[offset:]
                else:
                    marker_at = low.find(wrapped)
                    if marker_at < 0:
                        continue
                    offset = marker_at + len(wrapped)
                    raw = info.filename.strip("/")[offset:]
                if raw:
                    matches.append((info, PurePosixPath(raw)))
            return sorted(
                matches,
                key=lambda row: (str(row[1]).lower(), row[0].filename.lower()),
            )

        def extract(info: zipfile.ZipInfo, target: Path) -> None:
            data = zf.read(info)
            if not data:
                raise RuntimeError(
                    "official Pico source is empty in pinned v0.8.4 archive: "
                    f"{info.filename}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            recovered.append(info.filename)

        for source in PICO_RELEASE_FILES:
            relative = PurePosixPath(source).relative_to("assets")
            target = root.joinpath(*relative.parts)
            if target.is_file() and target.stat().st_size > 0:
                continue
            info = best_file_match(source)
            if info is None:
                raise RuntimeError(
                    "official Pico source missing from pinned v0.8.4 archive: "
                    f"{source}"
                )
            extract(info, target)

        for source in PICO_RELEASE_TREES:
            relative = PurePosixPath(source).relative_to("assets")
            target_dir = root.joinpath(*relative.parts)
            required = (
                target_dir / "Animation.json",
                target_dir / "spritemap1.json",
                target_dir / "spritemap1.png",
            )
            if all(path.is_file() and path.stat().st_size > 0 for path in required):
                continue
            matches = tree_matches(source)
            if not matches:
                raise RuntimeError(
                    "official Pico Animate atlas missing from pinned v0.8.4 archive: "
                    f"{source}"
                )
            for info, suffix in matches:
                extract(info, target_dir.joinpath(*suffix.parts))
            if not all(path.is_file() and path.stat().st_size > 0 for path in required):
                raise RuntimeError(
                    "official Pico Animate atlas incomplete after recovery: "
                    f"{source}"
                )

    return recovered


_RECOVERED_PICO_SOURCES = recover_official_pico_sources()
if _RECOVERED_PICO_SOURCES:
    print(
        "Recovered official Pico v0.8.4 sources from pinned Linux archive: "
        f"{len(_RECOVERED_PICO_SOURCES)} files"
    )


def pack_4bpp(indices: list[int], width: int, height: int) -> bytes:
    if width % 4:
        raise ValueError("4bpp width must be divisible by four")
    if len(indices) != width * height:
        raise ValueError("index buffer size mismatch")
    out = bytearray()
    for y in range(height):
        row = indices[y * width:(y + 1) * width]
        for x in range(0, width, 4):
            word = row[x] | (row[x + 1] << 4) | (row[x + 2] << 8) | (row[x + 1] << 12)
            # Correct the fourth nibble below; keeping the explicit expression
            # here makes the 4-pixel/16-bit packing order obvious.
            word = row[x] | (row[x + 1] << 4) | (row[x + 2] << 8) | (row[x + 3] << 12)
            out += struct.pack("<H", word)
    return bytes(out)


def common_palette(frames: list[Image.Image]) -> list[tuple[int, int, int]]:
    opaque: list[tuple[int, int, int]] = []
    for frame in frames:
        for r, g, b, a in frame.convert("RGBA").getdata():
            if a >= 128:
                opaque.append((r, g, b))
    if not opaque:
        raise RuntimeError("Boyfriend DJ frames contain no opaque pixels")

    width = min(4096, len(opaque))
    height = math.ceil(len(opaque) / width)
    src = Image.new("RGB", (width, height), opaque[-1])
    src.putdata(opaque + [opaque[-1]] * (width * height - len(opaque)))
    q = src.quantize(colors=15, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw = q.getpalette()[:45]
    colors = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
    while len(colors) < 15:
        colors.append((0, 0, 0))
    return colors[:15]


def frame_indices(frame: Image.Image, colors: list[tuple[int, int, int]]) -> list[int]:
    result: list[int] = []
    for r, g, b, a in frame.convert("RGBA").getdata():
        if a < 128:
            result.append(0)
            continue
        best = min(
            range(len(colors)),
            key=lambda i: (r - colors[i][0]) ** 2 + (g - colors[i][1]) ** 2 + (b - colors[i][2]) ** 2,
        )
        result.append(best + 1)
    return result


def write_tim_page(path: Path, template: dict[str, int], page_indices: list[int], colors: list[tuple[int, int, int]]) -> None:
    packed = pack_4bpp(page_indices, template["width"], template["height"])
    clut = [0] + [base.psx_color(c) for c in colors]
    clut_data = b"".join(struct.pack("<H", c) for c in clut)
    clut_block = struct.pack(
        "<I4H", 12 + len(clut_data),
        template["clut_x"], template["clut_y"], 16, 1,
    ) + clut_data
    image_block = struct.pack(
        "<I4H", 12 + len(packed),
        template["px"], template["py"], template["pw_words"], template["ph"],
    ) + packed
    path.write_bytes(struct.pack("<II", 0x10, 0x08) + clut_block + image_block)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets-root", type=Path, required=True)
    ap.add_argument("--upstream", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    root = args.assets_root / "images/freeplay/freeplay-boyfriend"
    anim_path = root / "Animation.json"
    map_path = root / "spritemap1.json"
    png_path = root / "spritemap1.png"
    animation = json.loads(anim_path.read_text())
    map_data = json.loads(map_path.read_text())
    atlas = Image.open(png_path).convert("RGBA")
    symbols = {s["SN"]: s for s in animation["SD"]["S"] if "SN" in s}
    sprites = {entry["SPRITE"]["name"]: entry["SPRITE"] for entry in map_data["ATLAS"]["SPRITES"]}
    if "Boyfriend DJ" not in symbols:
        raise SystemExit("official Animation.json has no Boyfriend DJ symbol")

    duration = dj.symbol_duration(symbols["Boyfriend DJ"])
    if duration != FRAME_COUNT:
        raise SystemExit(f"Boyfriend DJ timeline changed: expected {FRAME_COUNT} frames, found {duration}")

    frames = [
        base.fit(dj.render_dj_frame(atlas, sprites, symbols, frame_no), (FRAME_W, FRAME_H))
        for frame_no in range(FRAME_COUNT)
    ]
    palette = common_palette(frames)
    indexed = [frame_indices(frame, palette) for frame in frames]
    packed_frames = [pack_4bpp(buf, FRAME_W, FRAME_H) for buf in indexed]
    frame_bytes = FRAME_W * FRAME_H // 2
    if any(len(frame) != frame_bytes for frame in packed_frames):
        raise SystemExit("unexpected packed DJ frame size")

    menu_dir = args.upstream / "iso/menu"
    template = base.parse_tim_template(menu_dir / "title.tim")
    if (template["width"], template["height"]) != (256, 256):
        raise SystemExit("unexpected title TIM template size")

    page = [0] * (template["width"] * template["height"])
    first = indexed[0]
    for y in range(FRAME_H):
        page[y * template["width"]:y * template["width"] + FRAME_W] = first[y * FRAME_W:(y + 1) * FRAME_W]

    fpchar = menu_dir / "fpchar.tim"
    stream = menu_dir / "fpdj.bin"
    write_tim_page(fpchar, template, page, palette)
    stream.write_bytes(b"".join(packed_frames))

    expected_stream = FRAME_COUNT * frame_bytes
    if stream.stat().st_size != expected_stream:
        raise SystemExit(f"DJ stream size mismatch: {stream.stat().st_size} != {expected_stream}")

    report = json.loads(args.report.read_text())
    report["outputs"]["fpchar.tim"] = {
        "template": "title",
        "size": [256, 256],
        "bytes": fpchar.stat().st_size,
        "sha256": base.sha256(fpchar),
        "content": "official Boyfriend DJ frame 0 using the shared 14-frame stream palette",
        "sample_frames": [0, 4, 8, 12],
        "frame_size": [FRAME_W, FRAME_H],
        "frame_count": FRAME_COUNT,
    }
    report["dj_stream"] = {
        "file": "fpdj.bin",
        "bytes": stream.stat().st_size,
        "sha256": base.sha256(stream),
        "content": "14 official Boyfriend DJ flattened frames; shared 4bpp palette; RAM-resident stream",
        "frame_size": [FRAME_W, FRAME_H],
        "frame_count": FRAME_COUNT,
        "bytes_per_frame": frame_bytes,
    }
    report["policy"] = "official-v0.8.4-existing-files-only; all 14 DJ frames reconstructed from shipped Animate data; no replacement artwork"
    args.report.write_text(json.dumps(report, indent=2) + "\n")

    print(f"Built smooth Boyfriend DJ stream: {FRAME_COUNT} frames, {FRAME_W}x{FRAME_H}, {frame_bytes} bytes/frame")
    print(f"fpdj.bin bytes={stream.stat().st_size} sha256={base.sha256(stream)}")
    print(f"fpchar.tim sha256={base.sha256(fpchar)}")


if __name__ == "__main__":
    main()
