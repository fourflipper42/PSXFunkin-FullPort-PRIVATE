#!/usr/bin/env python3
"""Extract PSXFunkin character TIM pages from a built disc into readable previews."""
from __future__ import annotations

import argparse
import math
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw


GROUPS = {
    "pico-mixes": [
        "PICODARK.ARC", "PICOXMAS.ARC", "PICOHOLD.ARC", "PICOPIX.ARC",
        "NENEDARK.ARC", "NENEXMAS.ARC", "NENEPIX.ARC", "SPOOKYDK.ARC",
        "TANKBLDY.ARC", "OTIS.ARC",
    ],
    "weekend1": [
        "PICOPLAY.ARC", "NENE.ARC", "DARNELL.ARC", "PICOBL.ARC", "DARNBL.ARC",
    ],
    "sserafim": [
        "SFKAZ.ARC", "SFSAKU.ARC", "SFGF.ARC", "SFYUNJ.ARC", "SFCHAW.ARC", "SFEUNC.ARC",
    ],
    "base-weeks": [
        "MONSTER.ARC", "XMASBF.ARC", "XMASGF.ARC", "XMASP.ARC", "MONSTERX.ARC",
        "WEEBGF.ARC", "SENPAIM.ARC", "SPIRIT.ARC",
    ],
}


def arc_members(path: Path) -> list[tuple[str, bytes]]:
    data = path.read_bytes()
    entries: list[tuple[str, int]] = []
    for cursor in range(0, min(len(data), 4096), 16):
        raw_name = data[cursor:cursor + 12].split(b"\0", 1)[0]
        if not raw_name:
            break
        offset = struct.unpack_from("<I", data, cursor + 12)[0]
        if offset <= cursor or offset >= len(data):
            break
        entries.append((raw_name.decode("ascii", "replace"), offset))
    members = []
    for index, (name, offset) in enumerate(entries):
        end = entries[index + 1][1] if index + 1 < len(entries) else len(data)
        members.append((name, data[offset:end]))
    return members


def unpack_weekend_page(data: bytes) -> bytes:
    if data[:4] != b"W1R0":
        return data
    if len(data) < 12:
        raise ValueError("truncated W1R0 header")
    raw_size, packed_size = struct.unpack_from("<II", data, 4)
    src = memoryview(data)[12:12 + packed_size]
    if len(src) != packed_size:
        raise ValueError("truncated W1R0 payload")
    out = bytearray(); cursor = 0
    while cursor < len(src):
        control = src[cursor]; cursor += 1
        count = (control & 0x7F) + 1
        if control & 0x80:
            out.extend(b"\0" * count)
        else:
            if cursor + count > len(src):
                raise ValueError("truncated W1R0 literal")
            out.extend(src[cursor:cursor + count]); cursor += count
    if len(out) != raw_size:
        raise ValueError(f"W1R0 size mismatch: {len(out)} != {raw_size}")
    return bytes(out)


def checker(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGBA", size, (27, 29, 34, 255))
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], 16):
        for x in range(0, size[0], 16):
            if (x // 16 + y // 16) & 1:
                draw.rectangle((x, y, x + 15, y + 15), fill=(44, 47, 54, 255))
    return image


def card(name: str, pages: list[tuple[str, Image.Image]], page_limit: int | None) -> Image.Image:
    shown = pages if page_limit is None else pages[:page_limit]
    columns = min(4, max(1, len(shown)))
    rows = max(1, math.ceil(len(shown) / columns))
    width = columns * 272 + 16
    height = 34 + rows * 292
    result = Image.new("RGBA", (width, height), (16, 17, 21, 255))
    draw = ImageDraw.Draw(result)
    draw.text((12, 10), f"{name}  ({len(pages)} texture pages)", fill=(255, 255, 255, 255))
    for index, (member, page) in enumerate(shown):
        x = 8 + (index % columns) * 272
        y = 34 + (index // columns) * 292
        tile = checker((256, 256))
        fitted = page.convert("RGBA")
        if fitted.size != (256, 256):
            fitted.thumbnail((256, 256), Image.Resampling.NEAREST)
        tile.alpha_composite(fitted, ((256 - fitted.width) // 2, (256 - fitted.height) // 2))
        result.alpha_composite(tile, (x, y))
        draw.text((x, y + 260), member, fill=(205, 210, 220, 255))
    return result


def stack(cards: list[Image.Image], title: str) -> Image.Image:
    width = max([image.width for image in cards] + [720])
    height = 54 + sum(image.height + 14 for image in cards)
    result = Image.new("RGBA", (width, height), (8, 9, 12, 255))
    draw = ImageDraw.Draw(result)
    draw.text((14, 16), title, fill=(255, 208, 72, 255))
    y = 48
    for image in cards:
        result.alpha_composite(image, (0, y))
        y += image.height + 14
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--disc-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--decoder-root", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.decoder_root))
    from png_to_tim import decode_tim

    arcs = {path.name.upper(): path for path in args.disc_root.rglob("*.ARC")}
    args.output.mkdir(parents=True, exist_ok=True)
    individual = args.output / "individual"
    individual.mkdir(exist_ok=True)
    report = []

    for group, names in GROUPS.items():
        overview_cards = []
        for name in names:
            path = arcs.get(name)
            if path is None:
                report.append(f"MISSING {group}/{name}")
                continue
            pages = []
            for member, payload in arc_members(path):
                try:
                    pages.append((member, decode_tim(unpack_weekend_page(payload)).convert("RGBA")))
                except Exception as exc:
                    report.append(f"SKIP {name}/{member}: {exc}")
            if not pages:
                report.append(f"EMPTY {group}/{name}")
                continue
            card(name, pages, None).save(individual / f"{name.lower()}.png")
            overview_cards.append(card(name, pages, 2))
            report.append(f"OK {group}/{name}: {len(pages)} pages from {path.relative_to(args.disc_root)}")
        if overview_cards:
            stack(overview_cards, f"{group} exact PS1 sprite textures").save(args.output / f"{group}-overview.png")

    (args.output / "report.txt").write_text("\n".join(report) + "\n")
    print("\n".join(report))


if __name__ == "__main__":
    main()
