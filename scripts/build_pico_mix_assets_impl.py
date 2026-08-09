#!/usr/bin/env python3
"""Convert official Pico Mix character variants and Pico Freeplay visuals for PS1."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "ps1asset"))
from animateatlas_flatten import AnimateAtlas, render_leaves
from arc_pack import pack_arc
from png_to_tim import decode_tim, encode_tim

import build_freeplay_dj_stream as dj_stream
import build_freeplay_parity_v1 as freeplay
import build_v084_menu_visual_assets as menu_base
import build_charselect_source_v7 as charselect_v7
import build_charselect_v7_1_cleanup as charselect_v71
from build_sserafim_assets import merge_one
from build_weekend1_assets import lbl, sample_indices, sparrow_sequence, stage_fx_cell, write_char_module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def player_custom(manifest: dict, prefix: str, include_special: bool = False,
                  knife: bool = False) -> list[tuple[str, list[int], bool, int | None]]:
    custom = []
    for direction in ("Left", "Down", "Up", "Right"):
        custom.append((f"Miss_{direction}", lbl(manifest, prefix, f"{direction} Miss"), False, 0))
    if include_special:
        custom += [
            ("Hey", lbl(manifest, prefix, "Hey"), False, 0),
            ("Cheer", lbl(manifest, prefix, "Cheer"), False, 0),
            ("BurpShit", lbl(manifest, prefix, "*BURP* ... Shit"), False, 0),
            ("BurpSmile", lbl(manifest, prefix, "Burp Smile"), False, 0),
            ("BurpCensor", lbl(manifest, prefix, "Burp Censor"), False, 0),
        ]
    if knife:
        custom.append(("KnifeToss", lbl(manifest, prefix, "nene knife"), False, 0))
    return custom


def build_sparrow_manifest(base: Path, output: Path, prefix: str,
                           requests: list[tuple[str, int]], vram_x: int, clut_x: int) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    cells: list[tuple[str, Image.Image]] = []
    for label, count in requests:
        frames = sparrow_sequence(base, label)
        indices = [0] if count == 1 else sample_indices(len(frames), min(count, len(frames)))
        for index in indices:
            cells.append((label, stage_fx_cell(frames[index], 1.0)))
    pages = []
    frames = []
    label_map = {}
    for index, (label, _) in enumerate(cells):
        frame = {
            "index": index, "page": index // 4,
            "src": [(index % 2) * 128, ((index % 4) // 2) * 128, 128, 128],
            "offset": [64, 120], "label": f"{prefix}:{label}",
        }
        frames.append(frame)
        label_map.setdefault(frame["label"], []).append(index)
    for page_index in range(math.ceil(len(cells) / 4)):
        page = Image.new("RGBA", (256, 256))
        for slot in range(4):
            index = page_index * 4 + slot
            if index >= len(cells):
                break
            page.alpha_composite(cells[index][1], ((slot % 2) * 128, (slot // 2) * 128))
        member = f"{prefix}{page_index:02d}.tim"
        target = output / member
        data = encode_tim(page, 4, vram_x, 0, clut_x, 480)
        target.write_bytes(data)
        if decode_tim(data).size != (256, 256):
            raise RuntimeError(f"TIM verification failed: {target}")
        pages.append({"member": member, "path": str(target)})
    if len(pages) > 16:
        raise RuntimeError(f"{prefix}: {len(pages)} pages exceeds character archive limit")
    pack_arc(output / "main.arc", [Path(page["path"]) for page in pages], [page["member"] for page in pages])
    return {"pages": pages, "frames": frames, "label_map": label_map, "vram": [vram_x, 0, clut_x, 480]}


def build_pico_freeplay(root: Path, upstream: Path, validation: Path | None) -> dict:
    menu = upstream / "iso/menu"
    source = root / "images/freeplay"

    atlas = AnimateAtlas(source / "freeplay-pico")
    idle = next(label for label in atlas.labels() if label["name"] == "Idle")
    frames = [
        menu_base.fit(render_leaves(atlas.leaves_for_frame(idle["start"] + index))[0],
                      (dj_stream.FRAME_W, dj_stream.FRAME_H))
        for index in range(idle["duration"])
    ]
    palette = dj_stream.common_palette(frames)
    indexed = [dj_stream.frame_indices(frame, palette) for frame in frames]
    packed = [dj_stream.pack_4bpp(frame, dj_stream.FRAME_W, dj_stream.FRAME_H) for frame in indexed]
    stream = menu / "fppico.bin"
    stream.write_bytes(b"".join(packed))

    template = menu_base.parse_tim_template(menu / "title.tim")
    page = [0] * (template["width"] * template["height"])
    first = indexed[0]
    for y in range(dj_stream.FRAME_H):
        page[y * template["width"]:y * template["width"] + dj_stream.FRAME_W] = first[y * dj_stream.FRAME_W:(y + 1) * dj_stream.FRAME_W]
    tim = menu / "fppico.tim"
    dj_stream.write_tim_page(tim, template, page, palette)

    background = Image.new("RGBA", (256, 256))
    bg = menu_base.crop_4_3(Image.open(source / "freeplayBGweek1-pico.png").convert("RGBA")).resize((256, 192), Image.Resampling.LANCZOS)
    background.alpha_composite(bg, (0, 0))
    bg_tim = menu / "fpbgp.tim"
    menu_base.encode_tim4(background, menu_base.parse_tim_template(menu / "back.tim"), bg_tim)

    capsule_png = source / "freeplayCapsule/capsule/freeplayCapsule_pico.png"
    capsule_xml = source / "freeplayCapsule/capsule/freeplayCapsule_pico.xml"
    selector_png = source / "freeplaySelector/freeplaySelector_pico.png"
    selector_xml = source / "freeplaySelector/freeplaySelector_pico.xml"
    selected = freeplay.atlas_frames(capsule_png, capsule_xml, "mp3 capsule w backing0")
    unselected = freeplay.atlas_frames(capsule_png, capsule_xml, "mp3 capsule w backing NOT SELECTED")
    selectors = freeplay.atlas_frames(selector_png, selector_xml, "arrow pointer loop")
    if (len(selected), len(unselected), len(selectors)) != (8, 8, 15):
        raise RuntimeError("official Pico Freeplay animation counts changed")
    anim = Image.new("RGBA", freeplay.ANIM_SIZE)
    for index, frame in enumerate(selected):
        anim.alpha_composite(menu_base.fit(frame, freeplay.CAPSULE_SIZE), (0, index * freeplay.CAPSULE_SIZE[1]))
    for index, frame in enumerate(unselected):
        anim.alpha_composite(menu_base.fit(frame, freeplay.CAPSULE_SIZE), (freeplay.CAPSULE_SIZE[0], index * freeplay.CAPSULE_SIZE[1]))
    for index, frame in enumerate(selectors):
        x = freeplay.CAPSULE_SIZE[0] * 2 + (index % 3) * freeplay.SELECTOR_SIZE[0]
        y = (index // 3) * freeplay.SELECTOR_SIZE[1]
        anim.alpha_composite(menu_base.fit(frame, freeplay.SELECTOR_SIZE), (x, y))
    # Reuse only the official shared numeric/BPM glyph pixels from the BF atlas.
    bf_anim = decode_tim((menu / "fpanim.tim").read_bytes()).convert("RGBA")
    anim.alpha_composite(bf_anim.crop((0, freeplay.DIGIT_Y, 128, 224)), (0, freeplay.DIGIT_Y))
    anim_tim = menu / "fpanimp.tim"
    freeplay.write_tim4(anim, anim_tim, freeplay.ANIM_VRAM, freeplay.ANIM_CLUT)

    if validation is not None:
        validation.mkdir(parents=True, exist_ok=True)
        frames[0].save(validation / "pico-freeplay-idle.png")
        background.save(validation / "pico-freeplay-background.png")
        anim.save(validation / "pico-freeplay-ui.png")
    return {
        "idle_frames": idle["duration"], "frame_size": [dj_stream.FRAME_W, dj_stream.FRAME_H],
        "stream_bytes": stream.stat().st_size,
        "files": {path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)} for path in (stream, tim, bg_tim, anim_tim)},
    }


def build_bloody_tankman_health_icon(root: Path, upstream: Path,
                                     validation: Path | None) -> dict:
    """Build the official two-state bloody Tankman HUD icon as its own TIM.

    Keeping it separate avoids requantizing or changing a single pixel in the
    proven base HUD atlas. The runtime swaps to this texture at the chart's
    official SetHealthIcon event.
    """
    source = root / "images/icons/icon-tankman-bloody.png"
    if not source.is_file():
        raise RuntimeError("official icon-tankman-bloody.png missing")
    sheet = Image.open(source).convert("RGBA")
    if sheet.width != sheet.height * 2:
        raise RuntimeError(f"unexpected bloody Tankman icon size: {sheet.size}")
    icon = Image.new("RGBA", (48, 24), (0, 0, 0, 0))
    for state in range(2):
        frame = sheet.crop((state * sheet.height, 0, (state + 1) * sheet.height, sheet.height))
        icon.alpha_composite(frame.resize((24, 24), Image.Resampling.LANCZOS), (state * 24, 0))
    target = upstream / "iso/stage/pmblood.tim"
    target.write_bytes(encode_tim(icon, 8, 448, 256, 0, 509))
    if decode_tim(target.read_bytes()).size != icon.size:
        raise RuntimeError("bloody Tankman health TIM verification failed")
    if validation is not None:
        validation.mkdir(parents=True, exist_ok=True)
        icon.save(validation / "tankman-bloody-health-icon.png")
    return {
        "source": str(source.relative_to(root)), "frames": 2,
        "bytes": target.stat().st_size, "sha256": sha256(target),
    }


def pico_icon_frames(root: Path) -> tuple[list[Image.Image], Image.Image, str]:
    base = root / "images/freeplay/icons"
    png = base / "picopixel.png"
    xml = base / "picopixel.xml"
    if not (png.is_file() and xml.is_file()):
        raise RuntimeError("official freeplay/icons/picopixel.png/xml missing")
    nodes = list(ET.parse(xml).getroot())
    idle = [node for node in nodes if node.attrib.get("name", "").lower().startswith("idle0")]
    confirm = [node for node in nodes if node.attrib.get("name", "").lower().startswith("confirm0")]
    unique = []
    seen = set()
    for node in idle or nodes:
        key = tuple(node.attrib.get(name, "") for name in (
            "x", "y", "width", "height", "frameX", "frameY", "frameWidth", "frameHeight",
        ))
        if key not in seen:
            seen.add(key)
            unique.append(node)
    if not unique:
        raise RuntimeError("Pico PixelatedIcon contains no usable frames")
    while len(unique) < 4:
        unique += unique
    unique = unique[:4]
    frames = [charselect_v7.reconstruct_sparrow_frame(png, node) for node in unique]
    confirm_frame = charselect_v7.reconstruct_sparrow_frame(
        png, confirm[0] if confirm else unique[-1]
    )
    return frames, confirm_frame, str(png.relative_to(root))


def build_pico_controls(mod, root: Path, v7_meta: dict) -> tuple[Image.Image, dict]:
    selector = Image.open(root / "images/charSelect/charSelector.png").convert("RGBA")
    selector = selector.resize((41, 37), Image.Resampling.LANCZOS)

    def tint(color: tuple[int, int, int]) -> Image.Image:
        result = Image.new("RGBA", selector.size, (*color, 255))
        result.putalpha(selector.getchannel("A"))
        return result

    dark = tint((0x3C, 0x74, 0xF7))
    light = tint((0x3E, 0xBB, 0xFF))
    yellow = tint((0xFF, 0xFF, 0))
    orange = tint((0xFF, 0xCC, 0))
    confirm = charselect_v7.v5.first_sparrow_frame(
        charselect_v7.v6, root, "charSelectorConfirm.png", "charSelectorConfirm.xml"
    )
    deny = charselect_v7.v5.first_sparrow_frame(
        charselect_v7.v6, root, "charSelectorDenied.png", "charSelectorDenied.xml"
    )
    confirm = charselect_v71.alpha_crop(confirm).resize(selector.size, Image.Resampling.LANCZOS) if confirm else yellow.copy()
    deny = charselect_v71.alpha_crop(deny).resize(selector.size, Image.Resampling.LANCZOS) if deny else yellow.copy()

    source_icons, source_confirm, icon_path = pico_icon_frames(root)
    icons = [image.resize((43, 43), Image.Resampling.NEAREST) for image in source_icons]
    icon_confirm = source_confirm.resize((43, 43), Image.Resampling.NEAREST)
    pico_name = Image.open(root / "images/charSelect/picoNametag.png").convert("RGBA")
    tag_scale = 0.77 * (320 / 1280)
    pico_name = pico_name.resize(
        (max(1, round(pico_name.width * tag_scale)), max(1, round(pico_name.height * tag_scale))),
        Image.Resampling.LANCZOS,
    )
    locked_name = Image.open(root / "images/charSelect/lockedNametag.png").convert("RGBA")
    locked_name = locked_name.resize(
        (max(1, round(locked_name.width * tag_scale)), max(1, round(locked_name.height * tag_scale))),
        Image.Resampling.LANCZOS,
    )
    items = [(f"icon_idle_{index}", image) for index, image in enumerate(icons)]
    items += [
        ("icon_confirm", icon_confirm),
        ("cursor_dark", dark), ("cursor_light", light),
        ("cursor_yellow", yellow), ("cursor_orange", orange),
        ("cursor_confirm", confirm), ("cursor_deny", deny),
        ("name_pico", pico_name), ("name_locked", locked_name),
    ]
    atlas, rects = charselect_v7.shelf_pack(items)
    cursor_positions = v7_meta["controls"]["cursor_positions"]
    cursor_w, cursor_h = rects["cursor_yellow"][2:]
    center_x = cursor_positions[3][0] + cursor_w / 2
    center_y = cursor_positions[3][1] + cursor_h / 2
    icon_unselected = [round(center_x - 43 / 2), round(center_y - 43 / 2), 43, 43]
    icon_selected = [round(center_x - 56 / 2), round(center_y - 56 / 2), 56, 56]
    source_mid_x = round((1008 - 160) * 320 / 960)
    source_mid_y = round(100 * 240 / 720)
    name_pos = [
        min(320 - pico_name.width - 5, source_mid_x - pico_name.width // 2),
        source_mid_y - pico_name.height // 2,
    ]
    return atlas, {
        "rects": rects,
        "cursor_positions": cursor_positions,
        "icon_path": icon_path,
        "icon_idle_count": len(icons),
        "icon_unselected_dst": icon_unselected,
        "icon_selected_dst": icon_selected,
        "name_pico_pos": name_pos,
    }


def write_pico_charselect_header(path: Path, controls: dict, frame_count: int) -> None:
    rects = controls["rects"]
    lines = [
        "#ifndef CHARSELECT_PICO_GENERATED_H", "#define CHARSELECT_PICO_GENERATED_H", "",
        f"#define CSPICO_FRAME_COUNT {frame_count}",
        f"#define CSPICO_ICON_IDLE_COUNT {controls['icon_idle_count']}",
    ]
    for index in range(controls["icon_idle_count"]):
        x, y, w, h = rects[f"icon_idle_{index}"]
        lines += [
            f"#define CSPICO_ICON_IDLE_{index}_X {x}",
            f"#define CSPICO_ICON_IDLE_{index}_Y {y}",
            f"#define CSPICO_ICON_IDLE_{index}_W {w}",
            f"#define CSPICO_ICON_IDLE_{index}_H {h}",
        ]
    x, y, w, h = rects["icon_confirm"]
    lines += [
        f"#define CSPICO_ICON_CONFIRM_X {x}", f"#define CSPICO_ICON_CONFIRM_Y {y}",
        f"#define CSPICO_ICON_CONFIRM_W {w}", f"#define CSPICO_ICON_CONFIRM_H {h}",
    ]
    x, y, w, h = rects["name_pico"]
    lines += [
        f"#define CSPICO_NAME_X {x}", f"#define CSPICO_NAME_Y {y}",
        f"#define CSPICO_NAME_W {w}", f"#define CSPICO_NAME_H {h}",
        f"#define CSPICO_NAME_DST_X {controls['name_pico_pos'][0]}",
        f"#define CSPICO_NAME_DST_Y {controls['name_pico_pos'][1]}",
    ]
    ux, uy, uw, uh = controls["icon_unselected_dst"]
    sx, sy, sw, sh = controls["icon_selected_dst"]
    lines += [
        f"#define CSPICO_ICON_UNSEL_X {ux}", f"#define CSPICO_ICON_UNSEL_Y {uy}",
        f"#define CSPICO_ICON_UNSEL_W {uw}", f"#define CSPICO_ICON_UNSEL_H {uh}",
        f"#define CSPICO_ICON_SEL_X {sx}", f"#define CSPICO_ICON_SEL_Y {sy}",
        f"#define CSPICO_ICON_SEL_W {sw}", f"#define CSPICO_ICON_SEL_H {sh}",
        "static const short cspico_icon_src_x[CSPICO_ICON_IDLE_COUNT] = {" +
        ", ".join(str(rects[f"icon_idle_{i}"][0]) for i in range(controls["icon_idle_count"])) + "};",
        "static const short cspico_icon_src_y[CSPICO_ICON_IDLE_COUNT] = {" +
        ", ".join(str(rects[f"icon_idle_{i}"][1]) for i in range(controls["icon_idle_count"])) + "};",
        "", "#endif", "",
    ]
    path.write_text("\n".join(lines))


def build_pico_charselect(root: Path, upstream: Path, builder: Path,
                          charselect_report: Path, validation: Path | None) -> dict:
    clean = charselect_v7.corrected_builder_copy(builder)
    mod = charselect_v7.load_builder(clean)
    mod.SCENE_W = 320
    mod.SCENE_H = 240
    mod.CHAR_W = 320
    mod.CHAR_H = 240
    anims = {
        "bfChill": mod.load_optional_anim(root, "picoChill"),
        "gfChill": mod.load_optional_anim(root, "neneChill"),
        "lockedChill": mod.load_optional_anim(root, "lockedChill"),
    }
    if anims["bfChill"] is None or anims["gfChill"] is None:
        raise RuntimeError("official Pico/Nene Character Select Animate atlases missing")
    modes = (
        [("idle", i, charselect_v7.IDLE_COUNT) for i in range(charselect_v7.IDLE_COUNT)] +
        [("locked", i, charselect_v7.LOCKED_COUNT) for i in range(charselect_v7.LOCKED_COUNT)] +
        [("confirm", i, charselect_v7.CONFIRM_COUNT) for i in range(charselect_v7.CONFIRM_COUNT)] +
        [("deny", i, charselect_v7.DENY_COUNT) for i in range(charselect_v7.DENY_COUNT)]
    )
    frames = [
        mod.build_character_overlay(root, anims, mode, index, count)
        for mode, index, count in modes
    ]
    records = [charselect_v7.quantize_8bpp(frame, mod.base.psx_color) for frame in frames]
    blob = charselect_v7.pack_csq2(records)
    if charselect_v7.decode_csq2(blob) != records:
        raise RuntimeError("Pico Character Select CSQ2 round-trip failed")
    menu = upstream / "iso/menu"
    bank = menu / "cspico.rle"
    bank.write_bytes(blob)

    v7_report = json.loads(charselect_report.read_text())["character_select_source_v7"]
    atlas, controls = build_pico_controls(mod, root, v7_report)
    clut, pixels = charselect_v71.rgba8(atlas, mod.base.psx_color)
    for page, (vram_x, vram_y, _width) in enumerate(charselect_v71.CTRL_PAGES):
        payload = charselect_v71.tim8_page(
            clut, pixels, 256, 240, page * 128, 128,
            vram_x, vram_y, *charselect_v71.CTRL_CLUT,
        )
        (menu / f"cspc71{chr(97 + page)}.tim").write_bytes(payload)
    write_pico_charselect_header(
        upstream / "src/charselect_pico_generated.h", controls, len(frames)
    )
    if validation is not None:
        validation.mkdir(parents=True, exist_ok=True)
        frames[0].save(validation / "pico-character-select-idle.png")
        atlas.save(validation / "pico-character-select-controls.png")
    return {
        "slot": 3,
        "frames": len(frames),
        "bank_bytes": len(blob),
        "bank_sha256": sha256(bank),
        "icon_source": controls["icon_path"],
        "control_files": {
            name: {"bytes": (menu / name).stat().st_size, "sha256": sha256(menu / name)}
            for name in ("cspc71a.tim", "cspc71b.tim")
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--validation-dir", type=Path)
    parser.add_argument("--charselect-builder", type=Path, required=True)
    parser.add_argument("--charselect-report", type=Path, required=True)
    args = parser.parse_args()
    root, upstream = args.root, args.upstream
    build = upstream / "build-pico-mixes"
    shutil.rmtree(build, ignore_errors=True)
    build.mkdir(parents=True)
    charsrc = upstream / "src/character"
    records = {}

    dark_selection = {"Idle": 4, "Left": 2, "Down": 2, "Up": 2, "Right": 2,
                      "Left Miss": 2, "Down Miss": 2, "Up Miss": 2, "Right Miss": 2,
                      "Hey": 2, "Cheer": 2, "*BURP* ... Shit": 2, "Burp Smile": 2, "Burp Censor": 2}
    dark = merge_one(root, build / "picodark", "picodark", "pico-dark", "pk", 448, 0, dark_selection)
    dark_map = {"idle": lbl(dark, "pk", "Idle"), "left": lbl(dark, "pk", "Left"),
                "down": lbl(dark, "pk", "Down"), "up": lbl(dark, "pk", "Up"), "right": lbl(dark, "pk", "Right")}
    write_char_module(charsrc, "Char_PicoDark_New", "\\\\CHAR\\\\PICODARK.ARC;1", dark, "player", dark_map,
                      player_custom(dark, "pk", include_special=True), 3, (-50, -65, 100))

    xmas_selection = {"Idle": 4, "Left": 2, "Down": 2, "Up": 2, "Right": 2,
                      "Left Miss": 2, "Down Miss": 2, "Up Miss": 2, "Right Miss": 2,
                      "Death Intro": 3, "Death Loop": 4, "Death Confirm": 3}
    xmas = merge_one(root, build / "picoxmas", "picoxmas", "pico-christmas", "pc", 448, 0, xmas_selection)
    xmas_map = {"idle": lbl(xmas, "pc", "Idle"), "left": lbl(xmas, "pc", "Left"),
                "down": lbl(xmas, "pc", "Down"), "up": lbl(xmas, "pc", "Up"), "right": lbl(xmas, "pc", "Right"),
                "death_intro": lbl(xmas, "pc", "Death Intro"), "death_loop": lbl(xmas, "pc", "Death Loop"),
                "death_confirm": lbl(xmas, "pc", "Death Confirm")}
    write_char_module(charsrc, "Char_PicoXmas_New", "\\\\CHAR\\\\PICOXMAS.ARC;1", xmas, "player", xmas_map,
                      player_custom(xmas, "pc"), 3, (-50, -65, 100))

    hold_selection = {"idle": 4, "left": 2, "down ": 2, "up ": 2, "right": 2,
                      "left miss": 2, "down miss": 2, "up miss": 2, "right miss": 2,
                      "nene knife": 4, "laugh start": 2, "laugh loop": 2}
    hold = merge_one(root, build / "picohold", "picohold", "pico-holding-nene", "ph", 448, 0, hold_selection)
    # Normalize source labels so the shared custom builder can retain one enum layout.
    hold["label_map"]["ph:Left Miss"] = hold["label_map"]["ph:left miss"]
    hold["label_map"]["ph:Down Miss"] = hold["label_map"]["ph:down miss"]
    hold["label_map"]["ph:Up Miss"] = hold["label_map"]["ph:up miss"]
    hold["label_map"]["ph:Right Miss"] = hold["label_map"]["ph:right miss"]
    hold_map = {"idle": lbl(hold, "ph", "idle"), "left": lbl(hold, "ph", "left"),
                "down": lbl(hold, "ph", "down "), "up": lbl(hold, "ph", "up "), "right": lbl(hold, "ph", "right")}
    write_char_module(charsrc, "Char_PicoHold_New", "\\\\CHAR\\\\PICOHOLD.ARC;1", hold, "player", hold_map,
                      player_custom(hold, "ph", knife=True), 3, (-50, -65, 100))

    pico_pixel = build_sparrow_manifest(root / "shared/images/characters/picoPixel/picoPixel", build / "picopix", "pp", [
        ("idle", 4), ("left", 2), ("down", 2), ("up", 2), ("right", 2),
        ("leftmiss", 2), ("downmiss", 2), ("upmiss", 2), ("rightmiss", 2),
        ("firstDeath", 3), ("deathLoop", 4), ("deathConfirm", 3),
    ], 448, 0)
    for direction in ("Left", "Down", "Up", "Right"):
        pico_pixel["label_map"][f"pp:{direction} Miss"] = pico_pixel["label_map"][f"pp:{direction.lower()}miss"]
    pixel_map = {"idle": lbl(pico_pixel, "pp", "idle"), "left": lbl(pico_pixel, "pp", "left"),
                 "down": lbl(pico_pixel, "pp", "down"), "up": lbl(pico_pixel, "pp", "up"), "right": lbl(pico_pixel, "pp", "right"),
                 "death_intro": lbl(pico_pixel, "pp", "firstDeath"), "death_loop": lbl(pico_pixel, "pp", "deathLoop"),
                 "death_confirm": lbl(pico_pixel, "pp", "deathConfirm")}
    write_char_module(charsrc, "Char_PicoPixel_New", "\\\\CHAR\\\\PICOPIX.ARC;1", pico_pixel, "player", pixel_map,
                      player_custom(pico_pixel, "pp"), 3, (-50, -65, 100))

    for short, atlas_name, ctor, archive in (
        ("nd", "nene-dark", "Char_NeneDark_New", "NENEDARK.ARC"),
        ("nx", "nene-christmas", "Char_NeneXmas_New", "NENEXMAS.ARC"),
    ):
        selection = {"Idle": 4, "Knife Raise": 2, "Idle (holding Knife)": 2,
                     "Knife Lower": 2, "Laugh": 2, "Cheer": 2, "Fawn": 2}
        manifest = merge_one(root, build / short, short, atlas_name, short, 512, 16, selection)
        idle = lbl(manifest, short, "Idle")
        mapping = {"idle": idle, "left": idle, "down": lbl(manifest, short, "Fawn") or idle,
                   "up": idle, "right": idle}
        write_char_module(charsrc, ctor, f"\\\\CHAR\\\\{archive};1", manifest, "character", mapping, [], 4, (0, -50, 100))
        records[short] = manifest

    nene_pixel = build_sparrow_manifest(root / "shared/images/characters/nenePixel/nenePixel", build / "nenepix", "np",
                                        [("idle", 4), ("raise", 2), ("blink", 2), ("lower", 2)], 512, 16)
    np_idle = lbl(nene_pixel, "np", "idle")
    write_char_module(charsrc, "Char_NenePixel_New", "\\\\CHAR\\\\NENEPIX.ARC;1", nene_pixel, "character",
                      {"idle": np_idle, "left": np_idle, "down": np_idle, "up": np_idle, "right": np_idle}, [], 4, (0, -50, 100))

    spooky_dark = build_sparrow_manifest(root / "shared/images/characters/spooky_dark", build / "spookydark", "sd", [
        ("spooky dance idle", 4), ("note sing left", 2), ("spooky DOWN note", 2),
        ("spooky UP NOTE", 2), ("spooky sing right", 2), ("Spookiez YEAH cheer", 3),
    ], 576, 32)
    sd_idle = lbl(spooky_dark, "sd", "spooky dance idle")
    write_char_module(charsrc, "Char_SpookyDark_New", "\\\\CHAR\\\\SPOOKYDK.ARC;1", spooky_dark, "character", {
        "idle": sd_idle, "left": lbl(spooky_dark, "sd", "note sing left"),
        "down": lbl(spooky_dark, "sd", "spooky DOWN note"),
        "up": lbl(spooky_dark, "sd", "spooky UP NOTE"),
        "right": lbl(spooky_dark, "sd", "spooky sing right"),
    }, [("Cheer", lbl(spooky_dark, "sd", "Spookiez YEAH cheer"), False, 0)], 2, (0, -55, 100))

    bloody_selection = {"idle knife": 4, "left knife": 2, "down knife": 2,
                        "up knife": 2, "right knife": 2, "redheads": 6,
                        "pretty good bloody": 4}
    tank_bloody = merge_one(root, build / "tankbloody", "tankbloody", "tankman/bloody", "tb", 576, 32, bloody_selection)
    tb_idle = lbl(tank_bloody, "tb", "idle knife")
    write_char_module(charsrc, "Char_TankBloody_New", "\\\\CHAR\\\\TANKBLDY.ARC;1", tank_bloody, "character", {
        "idle": tb_idle, "left": lbl(tank_bloody, "tb", "left knife"),
        "down": lbl(tank_bloody, "tb", "down knife"), "up": lbl(tank_bloody, "tb", "up knife"),
        "right": lbl(tank_bloody, "tb", "right knife"),
    }, [("Redheads", lbl(tank_bloody, "tb", "redheads"), False, 0),
        ("PrettyGood", lbl(tank_bloody, "tb", "pretty good bloody"), False, 0)], 10, (0, -55, 100))

    otis_selection = {"idle": 4, "shoot left": 2, "shoot right": 2,
                      "shoot right low": 2, "shoot left low": 2}
    otis = merge_one(root, build / "otis", "otis", "otis", "ot", 512, 16, otis_selection)
    ot_idle = lbl(otis, "ot", "idle")
    write_char_module(charsrc, "Char_Otis_New", "\\\\CHAR\\\\OTIS.ARC;1", otis, "character", {
        "idle": ot_idle, "left": ot_idle, "down": ot_idle, "up": ot_idle, "right": ot_idle,
    }, [("ShootLeft", lbl(otis, "ot", "shoot left"), False, 0),
        ("ShootRight", lbl(otis, "ot", "shoot right"), False, 0),
        ("ShootRightLow", lbl(otis, "ot", "shoot right low"), False, 0),
        ("ShootLeftLow", lbl(otis, "ot", "shoot left low"), False, 0)], 4, (0, -50, 100))

    outputs = {
        "picodark.arc": dark, "picoxmas.arc": xmas, "picohold.arc": hold,
        "picopix.arc": pico_pixel, "nenedark.arc": records["nd"],
        "nenexmas.arc": records["nx"], "nenepix.arc": nene_pixel,
        "spookydk.arc": spooky_dark, "tankbldy.arc": tank_bloody, "otis.arc": otis,
    }
    for filename, manifest in outputs.items():
        source_dir = build / ({"picodark.arc": "picodark", "picoxmas.arc": "picoxmas", "picohold.arc": "picohold",
                              "picopix.arc": "picopix", "nenedark.arc": "nd", "nenexmas.arc": "nx", "nenepix.arc": "nenepix",
                              "spookydk.arc": "spookydark", "tankbldy.arc": "tankbloody", "otis.arc": "otis"}[filename])
        shutil.copyfile(source_dir / "main.arc", upstream / "iso" / filename)

    freeplay_report = build_pico_freeplay(root, upstream, args.validation_dir)
    health_icon_report = build_bloody_tankman_health_icon(root, upstream, args.validation_dir)
    charselect_report = build_pico_charselect(
        root, upstream, args.charselect_builder, args.charselect_report, args.validation_dir
    )
    report = {
        "policy": "authentic-v0.8.4-pico-mix-and-freeplay-source-frames-only",
        "characters": {name: {"frames": len(manifest["frames"]), "pages": len(manifest["pages"]),
                               "bytes": (upstream / "iso" / name).stat().st_size} for name, manifest in outputs.items()},
        "freeplay": freeplay_report,
        "character_select": charselect_report,
        "bloody_tankman_health_icon": health_icon_report,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
