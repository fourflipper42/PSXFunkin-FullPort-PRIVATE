#!/usr/bin/env python3
"""Build PS1 assets for the missing Week 2, Week 5, and Week 6 content.

The stage/character pages come from a pinned PSXFunkin conversion of the
authentic Funkin art. Winter Horrorland is composed directly from the official
v0.8.4 evilBG, evilTree, and evilSnow sources because the reference port does
not implement that stage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


REFERENCE_COMMIT = "b3f4c5ff0f7656af8ed17498de6b6d7b7a8d967e"
REFERENCE_ARCHIVE_SHA256 = "5853b706dc2b54677f9f659f206d0ce2eb7ca2c4aa88b66a492d50134a7bfbe0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def psx_color(rgb: tuple[int, int, int]) -> int:
    red, green, blue = rgb
    value = (red >> 3) | ((green >> 3) << 5) | ((blue >> 3) << 10)
    return 0x8000 if value == 0 else value


def read_tim_meta(path: Path) -> tuple[int, int, int, int, int]:
    values = [int(value) for value in path.read_text().split()]
    if len(values) != 5 or values[4] not in (4, 8):
        raise SystemExit(f"invalid TIM metadata {path}: {values}")
    return tuple(values)  # type: ignore[return-value]


def write_tim(source: Path, metadata: Path, output: Path) -> dict[str, object]:
    pixel_x, pixel_y, clut_x, clut_y, bpp = read_tim_meta(metadata)
    image = Image.open(source).convert("RGBA")
    divisor = 4 if bpp == 4 else 2
    padded_width = (image.width + divisor - 1) // divisor * divisor
    if padded_width != image.width:
        padded = Image.new("RGBA", (padded_width, image.height), (0, 0, 0, 0))
        padded.paste(image, (0, 0))
        image = padded

    alpha = image.getchannel("A")
    rgb = Image.new("RGB", image.size, (0, 0, 0))
    rgb.paste(image.convert("RGB"), mask=alpha)
    color_count = 15 if bpp == 4 else 255
    quantized = rgb.quantize(
        colors=color_count,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.FLOYDSTEINBERG,
    )
    palette = quantized.getpalette()[: color_count * 3]
    colors = [tuple(palette[index:index + 3]) for index in range(0, len(palette), 3)]
    while len(colors) < color_count:
        colors.append((0, 0, 0))

    indices = [
        0 if opacity < 128 else int(index) + 1
        for index, opacity in zip(quantized.getdata(), alpha.getdata())
    ]
    if bpp == 4:
        pixels = bytearray()
        for y in range(image.height):
            row = indices[y * image.width:(y + 1) * image.width]
            for x in range(0, image.width, 4):
                pixels += struct.pack(
                    "<H",
                    row[x] | (row[x + 1] << 4) | (row[x + 2] << 8) | (row[x + 3] << 12),
                )
        flags = 0x08
        clut_width = 16
    else:
        pixels = bytearray(indices)
        flags = 0x09
        clut_width = 256

    clut_values = [0] + [psx_color(color) for color in colors]
    clut_payload = b"".join(struct.pack("<H", value) for value in clut_values)
    clut_block = struct.pack(
        "<I4H", 12 + len(clut_payload), clut_x, clut_y, clut_width, 1,
    ) + clut_payload
    image_block = struct.pack(
        "<I4H", 12 + len(pixels), pixel_x, pixel_y, image.width // divisor, image.height,
    ) + pixels
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(struct.pack("<II", 0x10, flags) + clut_block + image_block)
    return {
        "source": source.as_posix(),
        "source_sha256": sha256(source),
        "source_size": [Image.open(source).width, Image.open(source).height],
        "padded_size": list(image.size),
        "bpp": bpp,
        "pixel_vram": [pixel_x, pixel_y, image.width // divisor, image.height],
        "clut_vram": [clut_x, clut_y, clut_width, 1],
        "output": output.as_posix(),
        "output_bytes": output.stat().st_size,
        "output_sha256": sha256(output),
    }


def pack_arc(files: list[Path], output: Path) -> dict[str, object]:
    if not files:
        raise ValueError("cannot build an empty archive")
    slots = max(16, len(files) + 1)
    position = slots * 16
    entries: list[tuple[bytes, int, bytes]] = []
    for path in files:
        name = path.name.encode("ascii")
        if len(name) > 12:
            raise SystemExit(f"archive filename too long: {path.name}")
        data = path.read_bytes()
        entries.append((name, position, data))
        position = (position + len(data) + 15) & ~15

    archive = bytearray(position)
    for index, (name, offset, data) in enumerate(entries):
        archive[index * 16:index * 16 + 12] = name.ljust(12, b"\0")
        struct.pack_into("<I", archive, index * 16 + 12, offset)
        archive[offset:offset + len(data)] = data
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(archive)
    return {
        "output": output.as_posix(),
        "files": [path.name for path in files],
        "bytes": len(archive),
        "sha256": sha256(output),
    }


def locate(root: Path, suffix: str) -> Path:
    normalized = suffix.lower().replace("\\", "/")
    matches = [
        path for path in root.rglob(Path(suffix).name)
        if path.is_file() and path.as_posix().lower().endswith(normalized)
    ]
    if not matches:
        raise SystemExit(f"official source missing below {root}: {suffix}")
    return sorted(matches, key=lambda path: (len(path.parts), path.as_posix()))[0]


def build_evil_stage(official_root: Path, output: Path, validation_dir: Path | None) -> dict[str, object]:
    sources = {
        "evilBG": locate(official_root, "week5/images/christmas/evilBG.png"),
        "evilTree": locate(official_root, "week5/images/christmas/evilTree.png"),
        "evilSnow": locate(official_root, "week5/images/christmas/evilSnow.png"),
    }
    world = Image.new("RGBA", (1600, 1200), (35, 6, 45, 255))
    background = Image.open(sources["evilBG"]).convert("RGBA")
    background = background.resize(
        (round(background.width * 0.8), round(background.height * 0.8)), Image.Resampling.LANCZOS,
    )
    world.alpha_composite(background, (-400, -500))
    world.alpha_composite(Image.open(sources["evilTree"]).convert("RGBA"), (300, -300))
    world.alpha_composite(Image.open(sources["evilSnow"]).convert("RGBA"), (-500, 700))
    composite = world.resize((256, 192), Image.Resampling.LANCZOS)
    page = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    page.paste(composite, (0, 0))

    temp_png = output.with_suffix(".source.png")
    temp_meta = output.with_suffix(".source.png.txt")
    temp_png.parent.mkdir(parents=True, exist_ok=True)
    page.save(temp_png)
    temp_meta.write_text("576 0 0 483 8\n")
    tim = write_tim(temp_png, temp_meta, output)
    temp_png.unlink()
    temp_meta.unlink()
    if validation_dir is not None:
        validation_dir.mkdir(parents=True, exist_ok=True)
        composite.save(validation_dir / "week5-winter-horrorland.png")
    return {
        "official_sources": {
            name: {"path": str(path.relative_to(official_root)), "sha256": sha256(path)}
            for name, path in sources.items()
        },
        "composition": {
            "world_crop": [0, 0, 1600, 1200],
            "background_position_scale": [-400, -500, 0.8],
            "tree_position": [300, -300],
            "snow_position": [-500, 700],
            "output_size": [256, 192],
        },
        "tim": tim,
    }


def contact_sheet(paths: list[Path], output: Path, label: str) -> None:
    thumb = (240, 180)
    columns = 3
    rows = (len(paths) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 260, rows * 215 + 35), (30, 30, 35))
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 10), label, fill=(255, 255, 255))
    for index, path in enumerate(paths):
        x = (index % columns) * 260 + 10
        y = (index // columns) * 215 + 35
        image = ImageOps.contain(Image.open(path).convert("RGBA"), thumb, Image.Resampling.NEAREST)
        tile = Image.new("RGBA", thumb, (10, 10, 12, 255))
        tile.alpha_composite(image, ((thumb[0] - image.width) // 2, (thumb[1] - image.height) // 2))
        sheet.paste(tile.convert("RGB"), (x, y))
        draw.text((x, y + 184), path.name, fill=(220, 220, 220))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def build_compact_xmas_parents(
    reference_iso: Path,
    upstream: Path,
    validation_dir: Path | None,
) -> tuple[list[dict[str, object]], dict[str, object], list[dict[str, object]]]:
    """Pack four half-resolution source frames per 4bpp page.

    The runtime draws these pages at 2x. This keeps all Mom/Dad note variants
    while reducing the persistent character archive from roughly 836 KiB to
    roughly 164 KiB, which is necessary for a real 2 MiB PlayStation.
    """
    stems = [
        "idle0", "idle1", "idle2", "idle3",
        "lefta0", "lefta1", "leftb0", "leftb1",
        "downa0", "downa1", "downb0", "downb1",
        "upa0", "upa1", "upb0", "upb1",
        "righta0", "righta1", "rightb0", "rightb1",
    ]
    output_dir = upstream / "iso/xmasp"
    output_dir.mkdir(parents=True, exist_ok=True)
    converted: list[dict[str, object]] = []
    mapping: list[dict[str, object]] = []
    tims: list[Path] = []
    for page_index in range(5):
        page = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        for slot in range(4):
            frame_index = page_index * 4 + slot
            source = reference_iso / "xmasp" / f"{stems[frame_index]}.png"
            frame = Image.open(source).convert("RGBA")
            resized = frame.resize(
                ((frame.width + 1) // 2, (frame.height + 1) // 2),
                Image.Resampling.LANCZOS,
            )
            x = (slot & 1) * 128
            y = (slot >> 1) * 128
            page.alpha_composite(resized, (x, y))
            mapping.append({
                "frame": frame_index,
                "name": stems[frame_index],
                "page": page_index,
                "source_rect": [x, y, resized.width, resized.height],
                "source_sha256": sha256(source),
            })
        source_page = output_dir / f"xmasp{page_index}.source.png"
        meta = output_dir / f"xmasp{page_index}.source.png.txt"
        tim = output_dir / f"xmasp{page_index}.tim"
        page.save(source_page)
        meta.write_text("448 256 0 481 4\n")
        converted.append(write_tim(source_page, meta, tim))
        source_page.unlink()
        meta.unlink()
        tims.append(tim)
    archive = pack_arc(tims, output_dir / "main.arc")
    if validation_dir is not None:
        contact_sheet(
            [reference_iso / "xmasp" / f"{stem}.png" for stem in stems],
            validation_dir / "week5-christmas-parents-frames.png",
            "All authentic Christmas Parents animation frames",
        )
    return converted, archive, mapping


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--official-root", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--validation-dir", type=Path)
    args = parser.parse_args()

    reference_iso = args.reference_root / "iso"
    if not (reference_iso / "week5/back0.png").is_file():
        raise SystemExit(f"pinned PSXFunkin reference is incomplete: {args.reference_root}")

    groups = {
        "monster/main.arc": ("monster", ["idle0", "idle1", "idle2", "left", "down", "up", "right"]),
        "bf/xmas.arc": ("bf", ["xmasbf0", "xmasbf1", "xmasbf2", "xmasbf3", "xmasbf4", "xmasbf5"]),
        "gf/xmas.arc": ("gf", ["xmasgf0", "xmasgf1", "xmasgf2"]),
        "monsterx/main.arc": ("monsterx", ["idle0", "idle1", "idle2", "left", "down", "up", "right"]),
        "gf/weeb.arc": ("gf", ["weeb0", "weeb1"]),
        "senpaim/main.arc": ("senpaim", ["senpai0", "senpai1"]),
        "spirit/main.arc": ("spirit", ["spirit0", "spirit1"]),
        "week5/back.arc": ("week5", ["back0", "back1", "back2", "back3", "back4", "back5"]),
        "week6/back.arc": ("week6", ["back0", "back1", "back2"]),
    }

    converted: list[dict[str, object]] = []
    archives: list[dict[str, object]] = []
    for archive_rel, (source_dir, stems) in groups.items():
        tims: list[Path] = []
        for stem in stems:
            source = reference_iso / source_dir / f"{stem}.png"
            metadata = source.with_suffix(".png.txt")
            if not source.is_file() or not metadata.is_file():
                raise SystemExit(f"missing pinned conversion source: {source}")
            destination = args.upstream / "iso" / source_dir / f"{stem}.tim"
            converted.append(write_tim(source, metadata, destination))
            tims.append(destination)

        if archive_rel == "bf/xmas.arc":
            # Only the BREAK page is persistent. Mic-drop/retry pages are
            # streamed from the existing BFDEAD.ARC by the player runtime.
            for name in ("dead0.tim",):
                source = args.upstream / "iso/bf" / name
                if not source.is_file():
                    raise SystemExit(f"Boyfriend death asset missing: {source}")
                tims.append(source)
        archive_path = args.upstream / "iso" / archive_rel
        archives.append(pack_arc(tims, archive_path))

    xmasp_converted, xmasp_archive, xmasp_mapping = build_compact_xmas_parents(
        reference_iso, args.upstream, args.validation_dir,
    )
    converted.extend(xmasp_converted)
    archives.append(xmasp_archive)

    back3_source = reference_iso / "week6/back3.png"
    converted.append(write_tim(
        back3_source,
        back3_source.with_suffix(".png.txt"),
        args.upstream / "iso/week6/back3.tim",
    ))
    evil = build_evil_stage(
        args.official_root,
        args.upstream / "iso/week5/evil.tim",
        args.validation_dir,
    )

    if args.validation_dir is not None:
        contact_sheet(
            [reference_iso / "week5" / f"back{index}.png" for index in range(6)],
            args.validation_dir / "week5-mall-pages.png",
            "Week 5 authentic PS1 conversion pages",
        )
        contact_sheet(
            [reference_iso / "week6" / f"back{index}.png" for index in range(4)],
            args.validation_dir / "week6-school-pages.png",
            "Week 6 authentic PS1 conversion pages",
        )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "policy": "authentic-funkin-art-only-no-generated-art",
        "reference": {
            "repository": "Nintendo-Bro385/PSXFunkin-Flop-Engine",
            "commit": REFERENCE_COMMIT,
            "expected_codeload_sha256": REFERENCE_ARCHIVE_SHA256,
            "license": "MPL-2.0 source adaptation; Funkin art remains under its upstream terms",
        },
        "coverage": {
            "week2": ["Monster character", "existing spooky mansion lightning texture activated by runtime patch"],
            "week5": ["mall layers", "Santa", "Christmas BF/GF/Parents", "Christmas Monster", "Winter Horrorland"],
            "week6": ["school layers", "background freaks", "evil school", "pixel GF", "angry Senpai", "Spirit"],
        },
        "converted_tim_count": len(converted) + 1,
        "converted": converted,
        "archives": archives,
        "winter_horrorland": evil,
        "christmas_parents": {
            "policy": "all 20 authentic frames retained; half-resolution 4bpp pages drawn at 2x for 2 MiB RAM",
            "mapping": xmasp_mapping,
            "archive_bytes": xmasp_archive["bytes"],
        },
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "converted_tim_count": report["converted_tim_count"],
        "archive_count": len(archives),
        "report": str(args.report),
    }, indent=2))


if __name__ == "__main__":
    main()
