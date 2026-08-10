#!/usr/bin/env python3
"""Convert the official LE SSERAFIM collaboration artwork for PSXFunkin."""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "ps1asset"))
from animateatlas_flatten import AnimateAtlas, render_leaves
from arc_pack import pack_arc
from build_character_pages import build as build_pages
from png_to_tim import decode_tim, encode_tim

from build_weekend1_assets import lbl, sample_indices, stage_fx_cell, write_char_module


def trim_manifest(manifest: dict, component: Path, rules: dict[str, int],
                  prefix: str, vram_x: int, clut_x: int) -> dict:
    """Repack only gameplay-used authentic samples to respect PS1 main RAM."""
    selected = []
    for label, count in rules.items():
        matches = [frame for frame in manifest["frames"] if frame["label"] == label]
        if not matches:
            raise RuntimeError(f"{prefix}: required official animation missing: {label}")
        keep = min(count, len(matches))
        indices = [0] if keep == 1 else sample_indices(len(matches), keep)
        for index in indices:
            selected.append(dict(matches[index]))

    pages_dir = component / "trimmed-pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    for new_index, frame in enumerate(selected):
        frame["index"] = new_index
        frame["page"] = new_index // 4
        frame["src"] = [(new_index % 2) * 128, ((new_index % 4) // 2) * 128, 128, 128]
    for page_index in range(math.ceil(len(selected) / 4)):
        page = Image.new("RGBA", (256, 256))
        for slot in range(4):
            index = page_index * 4 + slot
            if index >= len(selected):
                break
            cell = Image.open(component / selected[index]["cell"]).convert("RGBA")
            page.alpha_composite(cell, ((slot % 2) * 128, (slot // 2) * 128))
        target = pages_dir / f"{prefix}{page_index:02d}.tim"
        data = encode_tim(page, 4, vram_x, 0, clut_x, 480)
        target.write_bytes(data)
        if decode_tim(data).size != (256, 256):
            raise RuntimeError(f"TIM verification failed: {target}")
        pages.append({"index": page_index, "tim": str(target.relative_to(component)), "bytes": len(data)})

    manifest = dict(manifest)
    manifest["frames"] = selected
    manifest["pages"] = pages
    manifest["ram_policy"] = "gameplay-used official samples only"
    return manifest


def merge_one(root: Path, out: Path, name: str, atlas_subdir: str, prefix: str,
              vram_x: int, clut_x: int, selection: dict[str, int]) -> dict:
    component = out / "component"
    manifest = build_pages(
        root / "shared/images/characters" / atlas_subdir,
        component, prefix, 4, vram_x, 0, clut_x, 480, "all", selection,
    )
    manifest = trim_manifest(manifest, component, selection, prefix, vram_x, clut_x)
    pages = []
    for page in manifest["pages"]:
        source = component / page["tim"]
        member = f"{prefix}{page['index']:02d}.tim"
        target = out / member
        shutil.copyfile(source, target)
        pages.append({"member": member, "path": str(target)})
    if len(pages) > 16:
        raise RuntimeError(f"{name}: {len(pages)} pages exceeds the runtime archive limit")
    pack_arc(out / "main.arc", [Path(page["path"]) for page in pages], [page["member"] for page in pages])
    frames = []
    label_map = {}
    for frame in manifest["frames"]:
        item = dict(frame)
        item["label"] = f"{prefix}:{frame['label']}"
        frames.append(item)
        label_map.setdefault(item["label"], []).append(item["index"])
    merged = {
        "name": name,
        "pages": pages,
        "frames": frames,
        "label_map": label_map,
        "vram": [vram_x, 0, clut_x, 480],
    }
    (out / "manifest.json").write_text(json.dumps(merged, indent=2))
    return merged


def atlas_images(atlas_dir: Path, requests: list[tuple[str, int]]) -> list[tuple[str, Image.Image]]:
    atlas = AnimateAtlas(atlas_dir)
    labels = {label["name"]: label for label in atlas.labels()}
    output = []
    for name, count in requests:
        label = labels[name]
        indices = [label["duration"] // 2] if count == 1 else sample_indices(label["duration"], count)
        for frame in indices:
            image, _ = render_leaves(atlas.leaves_for_frame(label["start"] + frame))
            output.append((name, stage_fx_cell(image, 1.0)))
    return output


def pack_sprite_arc(cells: list[tuple[str, Image.Image]], out: Path, arc_name: str,
                    prefix: str, vram_x: int, clut_x: int) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    pages = []
    frames = {}
    for index, (label, _) in enumerate(cells):
        frames.setdefault(label, []).append({
            "tex": index // 4,
            "src": [(index % 2) * 128, ((index % 4) // 2) * 128, 128, 128],
        })
    for page_index in range(math.ceil(len(cells) / 4)):
        page = Image.new("RGBA", (256, 256))
        for slot in range(4):
            index = page_index * 4 + slot
            if index >= len(cells):
                break
            page.alpha_composite(cells[index][1], ((slot % 2) * 128, (slot // 2) * 128))
        path = out / f"{prefix}{page_index:02d}.tim"
        data = encode_tim(page, 4, vram_x, 0, clut_x, 480)
        path.write_bytes(data)
        if decode_tim(data).size != (256, 256):
            raise RuntimeError(f"TIM verification failed: {path}")
        pages.append(path)
    pack_arc(out / arc_name, pages, [page.name for page in pages])
    return {"pages": len(pages), "frames": frames, "members": [page.name for page in pages]}


def place(canvas: Image.Image, source: Path, position: tuple[float, float], scale: float,
          xref: float = 620.0, yref: float = 400.0) -> None:
    image = Image.open(source).convert("RGBA")
    image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    x = round(256 + (position[0] - xref) * scale)
    y = round(120 + (position[1] - yref) * scale)
    canvas.alpha_composite(image, (x, y))


def build_background(root: Path, out: Path) -> dict:
    images = root / "sserafim/images"
    canvas = Image.new("RGBA", (512, 240), (245, 218, 190, 255))
    layers = [
        ("bg.png", (-1853, -815)),
        ("floor.png", (120, 625)),
        ("back-tables.png", (-1857, 267)),
        ("back-stools.png", (-1357, 426)),
        ("truck-stuff.png", (-983, -707)),
        ("truck-door.png", (-980, -173)),
        ("front-stool.png", (-280, 818)),
    ]
    for name, position in layers:
        place(canvas, images / name, position, 0.22)
    out.mkdir(parents=True, exist_ok=True)
    canvas.save(out / "sserafim_preview.png")
    pages = []
    for index, (vram_x, clut_x) in enumerate(((640, 48), (704, 64))):
        page = canvas.crop((index * 256, 0, (index + 1) * 256, 240))
        data = encode_tim(page, 4, vram_x, 0, clut_x, 480)
        target = out / f"back{index}.tim"
        target.write_bytes(data)
        pages.append(target)
    pack_arc(out / "back.arc", pages, ["back0.tim", "back1.tim"])
    return {"layers": [name for name, _ in layers], "preview": str(out / "sserafim_preview.png")}


def icon_cell(root: Path) -> Image.Image:
    names = ["bf", "gf", "yunjin", "kazuha", "chaewon", "eunchae", "sakura"]
    cell = Image.new("RGBA", (128, 128))
    for index, name in enumerate(names):
        path = root / f"images/icons/icon-{name}.png"
        image = Image.open(path).convert("RGBA")
        # Health icons are horizontal two-state sheets in v0.8.4.
        side = min(image.height, image.width // 2 if image.width >= image.height * 2 else image.width)
        image = image.crop((0, 0, side, side)).resize((24, 24), Image.Resampling.LANCZOS)
        cell.alpha_composite(image, ((index % 4) * 30 + 3, (index // 4) * 30 + 3))
    return cell


def build_fx(root: Path, out: Path) -> dict:
    images = root / "sserafim/images"
    cells = [
        ("truck1", stage_fx_cell(Image.open(images / "lights/truck-light1.png").convert("RGBA"), 0.22)),
        ("truck2", stage_fx_cell(Image.open(images / "lights/truck-light2.png").convert("RGBA"), 0.22)),
        ("icons", icon_cell(root)),
        ("dust", stage_fx_cell(Image.open(images / "dust/dustMid.png").convert("RGBA"), 0.08)),
    ]
    result = pack_sprite_arc(cells, out, "fx.arc", "sf", 960, 128)
    result["labels"] = [name for name, _ in cells]
    return result


def write_extra_header(path: Path, records: dict[str, dict]) -> None:
    lines = ["#ifndef _SSERAFIM_ASSETS_GENERATED_H", "#define _SSERAFIM_ASSETS_GENERATED_H", ""]
    for girl, record in records.items():
        for label, rows in record["frames"].items():
            ident = "".join(ch if ch.isalnum() else "_" for ch in label.lower())
            lines.append(f"static const SserafimSpriteFrame sf_{girl}_{ident}[] = {{")
            for row in rows:
                x, y, w, h = row["src"]
                lines.append(f"    {{{row['tex']}, {{{x},{y},{w},{h}}}}},")
            lines.append("};")
            lines.append(f"#define SF_{girl.upper()}_{ident.upper()}_COUNT {len(rows)}")
        lines.append("")
    lines.extend(["#endif", ""])
    path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root, upstream = args.root, args.upstream
    build = upstream / "build-sserafim"
    shutil.rmtree(build, ignore_errors=True)
    build.mkdir(parents=True)
    charsrc = upstream / "src/character"

    kazuha = merge_one(root, build / "kazuha", "kazuha", "sserafim/kazuha", "kz", 448, 0, {
        "idle": 4, "left": 2, "down": 2, "up": 2, "right": 2,
    })
    kzmap = {
        "idle": lbl(kazuha, "kz", "idle"), "left": lbl(kazuha, "kz", "left"),
        "down": lbl(kazuha, "kz", "down"), "up": lbl(kazuha, "kz", "up"),
        "right": lbl(kazuha, "kz", "right"),
    }
    write_char_module(charsrc, "Char_SFKazuha_New", "\\CHAR\\SFKAZ.ARC;1", kazuha,
                      "character", kzmap, [], 2, (36, -54, 100))

    sakura_selection = {"idle": 4}
    for direction in ("left", "down", "up", "right"):
        sakura_selection[f"sakura pose {direction}"] = 2
        sakura_selection[f"joint pose {direction}"] = 1
        sakura_selection[f"bf {direction} 1"] = 1
        sakura_selection[f"bf {direction} 2"] = 1
        sakura_selection[f"sakura {direction} miss"] = 1
        sakura_selection[f"joint {direction} miss"] = 1
        sakura_selection[f"style {direction} miss"] = 1
    sakura = merge_one(root, build / "sakura", "sakura", "sserafim/sakura", "sk", 512, 16, sakura_selection)
    skmap = {
        "idle": lbl(sakura, "sk", "idle"),
        "left": lbl(sakura, "sk", "sakura pose left"),
        "down": lbl(sakura, "sk", "sakura pose down"),
        "up": lbl(sakura, "sk", "sakura pose up"),
        "right": lbl(sakura, "sk", "sakura pose right"),
    }
    custom = []
    for family, prefix in (("Joint", "joint pose"), ("BF1", "bf"), ("BF2", "bf")):
        for direction in ("left", "down", "up", "right"):
            label = f"{prefix} {direction}"
            if family == "BF1": label += " 1"
            if family == "BF2": label += " 2"
            custom.append((f"{family}_{direction.title()}", lbl(sakura, "sk", label), False, 0))
    for family, prefix in (("BaseMiss", "sakura"), ("JointMiss", "joint"), ("StyleMiss", "style")):
        for direction in ("left", "down", "up", "right"):
            custom.append((f"{family}_{direction.title()}", lbl(sakura, "sk", f"{prefix} {direction} miss"), False, 0))
    write_char_module(charsrc, "Char_SFSakura_New", "\\CHAR\\SFSAKU.ARC;1", sakura,
                      "player", skmap, custom, 0, (-42, -60, 100))

    gf_selection = {"danceLeft": 4, "danceRight": 4}
    for direction in ("left", "down", "up", "right"):
        gf_selection[f"{direction} 1"] = 2
        gf_selection[f"{direction} 2"] = 2
        gf_selection[f"{direction} miss 2"] = 1
    girlfriend = merge_one(root, build / "gf", "gf", "sserafim/sserafim-gf", "sg", 576, 32, gf_selection)
    gfmap = {
        "idle": lbl(girlfriend, "sg", "danceLeft"),
        "left": lbl(girlfriend, "sg", "left 1"), "down": lbl(girlfriend, "sg", "down 1"),
        "up": lbl(girlfriend, "sg", "up 1"), "right": lbl(girlfriend, "sg", "right 1"),
    }
    gfcustom = [("DanceRight", lbl(girlfriend, "sg", "danceRight"), False, 0)]
    for family, suffix in (("Beautiful", "2"), ("BeautifulMiss", "miss 2")):
        for direction in ("left", "down", "up", "right"):
            gfcustom.append((f"{family}_{direction.title()}", lbl(girlfriend, "sg", f"{direction} {suffix}"), False, 0))
    write_char_module(charsrc, "Char_SFGF_New", "\\CHAR\\SFGF.ARC;1", girlfriend,
                      "character", gfmap, gfcustom, 1, (0, -45, 100))

    extras = {}
    extra_specs = {
        "yunjin": ("yunjin", 768, 80, [("doorclosed", 1), ("idle", 1), ("left", 1), ("down", 1), ("up", 1), ("right", 1), ("kick1", 4), ("kick2", 10)]),
        "chaewon": ("chaewon", 832, 96, [("idle", 1), ("left", 1), ("down", 1), ("up", 1), ("right", 1)]),
        "eunchae": ("eunchae", 896, 112, [("idle", 1), ("left", 1), ("down", 1), ("up", 1), ("right", 1)]),
    }
    extra_iso_names = {"yunjin": "sfyunj.arc", "chaewon": "sfchaw.arc", "eunchae": "sfeunc.arc"}
    for name, (folder, vram_x, clut_x, requests) in extra_specs.items():
        cells = atlas_images(root / "shared/images/characters/sserafim" / folder, requests)
        record = pack_sprite_arc(cells, build / name, f"{name}.arc", name[:2], vram_x, clut_x)
        extras[name] = record
        shutil.copyfile(build / name / f"{name}.arc", upstream / "iso" / extra_iso_names[name])

    stage_dir = upstream / "iso/sserafim"
    background = build_background(root, build / "background")
    stage_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(build / "background/back.arc", stage_dir / "back.arc")
    fx = build_fx(root, build / "fx")
    shutil.copyfile(build / "fx/fx.arc", stage_dir / "fx.arc")
    write_extra_header(upstream / "src/sserafim_assets_generated.h", extras)

    for source, target in (
        (build / "kazuha/main.arc", upstream / "iso/sfkaz.arc"),
        (build / "sakura/main.arc", upstream / "iso/sfsaku.arc"),
        (build / "gf/main.arc", upstream / "iso/sfgf.arc"),
    ):
        shutil.copyfile(source, target)

    report = {
        "policy": "authentic-v0.8.4-le-sserafim-source-frames-only",
        "characters": {
            "kazuha": {"frames": len(kazuha["frames"]), "pages": len(kazuha["pages"])},
            "sakura": {"frames": len(sakura["frames"]), "pages": len(sakura["pages"])},
            "girlfriend": {"frames": len(girlfriend["frames"]), "pages": len(girlfriend["pages"])},
        },
        "extras": {name: {"pages": value["pages"], "frames": sum(len(rows) for rows in value["frames"].values())} for name, value in extras.items()},
        "background": background,
        "fx": fx,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
