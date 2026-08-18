#!/usr/bin/env python3
"""Merge the user's supplied Funkin mod archives into one PS2 build asset tree.

This deliberately does NOT copy HScript/HXC into the disc. Script-heavy mods
are reimplemented in native PS2 code; this importer supplies their data/art.
It also unpacks .fnfc song capsules into normal data/songs + songs directories.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

STANDARD_DIRS = (
    "data",
    "images",
    "songs",
    "music",
    "sounds",
    "fonts",
    "videos",
    "shared",
)


def load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def safe_extract(zf: zipfile.ZipFile, destination: Path) -> None:
    destination = destination.resolve()
    for info in zf.infolist():
        member = PurePosixPath(info.filename)
        if member.is_absolute() or ".." in member.parts:
            raise ValueError(f"unsafe archive path: {info.filename}")
        target = destination.joinpath(*member.parts).resolve()
        if destination not in target.parents and target != destination:
            raise ValueError(f"archive escapes destination: {info.filename}")
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def locate_mod_root(extracted: Path) -> Path:
    if (extracted / "_polymod_meta.json").exists():
        return extracted
    candidates = [p.parent for p in extracted.rglob("_polymod_meta.json")]
    if len(candidates) == 1:
        return candidates[0]
    top_dirs = [p for p in extracted.iterdir() if p.is_dir()]
    if len(top_dirs) == 1:
        return top_dirs[0]
    return extracted


def metadata(root: Path) -> dict:
    path = root / "_polymod_meta.json"
    if not path.exists():
        return {"title": root.name, "id": root.name.lower().replace(" ", "-")}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"title": root.name, "id": root.name.lower().replace(" ", "-")}


def overlay_dir(source: Path, destination: Path) -> int:
    copied = 0
    if not source.is_dir():
        return copied
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


def merge_standard_assets(root: Path, assets_root: Path) -> int:
    copied = 0
    for name in STANDARD_DIRS:
        source = root / name
        if source.is_dir():
            copied += overlay_dir(source, assets_root / name)
    return copied


def unpack_fnfc_bytes(data: bytes, assets_root: Path, source_name: str) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as capsule:
        manifest = json.loads(capsule.read("manifest.json").decode("utf-8-sig"))
        song_id = str(manifest.get("songId") or "").strip()
        if not song_id:
            raise ValueError(f"{source_name}: .fnfc manifest has no songId")
        data_dir = assets_root / "data" / "songs" / song_id
        audio_dir = assets_root / "songs" / song_id
        data_dir.mkdir(parents=True, exist_ok=True)
        audio_dir.mkdir(parents=True, exist_ok=True)
        data_files = 0
        audio_files = 0
        for info in capsule.infolist():
            if info.is_dir() or info.filename == "manifest.json":
                continue
            name = PurePosixPath(info.filename).name
            if not name or ".." in PurePosixPath(info.filename).parts:
                continue
            payload = capsule.read(info)
            suffix = Path(name).suffix.lower()
            if suffix == ".json":
                (data_dir / name).write_bytes(payload)
                data_files += 1
            elif suffix in (".ogg", ".wav", ".mp3"):
                (audio_dir / name).write_bytes(payload)
                audio_files += 1
        return {
            "source": source_name,
            "songId": song_id,
            "dataFiles": data_files,
            "audioFiles": audio_files,
        }


def unpack_fnfcs_from_archive(archive: Path, assets_root: Path) -> list[dict]:
    result: list[dict] = []
    with zipfile.ZipFile(archive) as outer:
        for info in outer.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".fnfc"):
                continue
            result.append(unpack_fnfc_bytes(outer.read(info), assets_root, info.filename))
    return result


def find_named_archive(archives: list[Path], needles: tuple[str, ...]) -> Path | None:
    for archive in archives:
        name = archive.name.lower()
        if all(needle in name for needle in needles):
            return archive
    return None


def copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    overlay_dir(source, destination)


def convert_extras(
    merged_assets: Path,
    extracted_roots: dict[str, Path],
    disc_game: Path,
) -> dict:
    texture = load_module("convert_texture.py", "convert_texture_modpack")
    atlas = load_module("convert_sparrow_atlas.py", "convert_atlas_modpack")
    health_icons = load_module("convert_health_icons.py", "convert_health_icons_modpack")
    balphabet = load_module("convert_better_alphabet.py", "convert_better_alphabet_modpack")
    pins = load_module("convert_pointless_pins.py", "convert_pointless_pins_modpack")
    result: dict = {}

    # Health icons are converted after Tower's overlay has replaced base icon PNGs.
    characters_root = merged_assets / "data" / "characters"
    character_ids = sorted(p.stem for p in characters_root.glob("*.json")) if characters_root.is_dir() else []
    result["healthIcons"] = health_icons.convert(
        merged_assets,
        character_ids,
        disc_game,
        strict=False,
    )

    # Better Alphabet + Pointless Pins extend the same font namespace. Because
    # their asset folders were merged first, ppicons.txt/PNG are included too.
    if (merged_assets / "data" / "balphabet" / "default" / "default.json").exists():
        result["betterAlphabet"] = balphabet.convert(
            merged_assets,
            disc_game / "FONT" / "BALPH",
        )

    pins_json = merged_assets / "data" / "pointlesspins" / "pins.json"
    boxes_json = merged_assets / "data" / "pointlesspins" / "boxes.json"
    if pins_json.exists() and boxes_json.exists():
        result["pointlessPins"] = pins.convert(
            pins_json,
            boxes_json,
            disc_game / "PINS" / "PINS.FPIN",
            disc_game / "PINS" / "PINS.JSON",
        )

    # Fully Customizable HUD visual extras.
    modhud = disc_game / "MODHUD"
    for source_name, target_name in (("FC.png", "FC.FPTX"), ("FC1.png", "FC1.FPTX")):
        source = merged_assets / "images" / source_name
        if source.exists():
            modhud.mkdir(parents=True, exist_ok=True)
            texture.convert(source, modhud / target_name)

    # Combos Reimplemented art. Runtime falls back to text if these are absent.
    for stem in ("combo", "combo-pixel"):
        source = merged_assets / "images" / f"{stem}.png"
        if source.exists():
            modhud.mkdir(parents=True, exist_ok=True)
            texture.convert(source, modhud / f"{stem.upper()}.FPTX")
    for stem in ("noteCombo", "noteComboNumbers"):
        png = merged_assets / "images" / f"{stem}.png"
        xml = merged_assets / "images" / f"{stem}.xml"
        if png.exists() and xml.exists():
            atlas.convert(png, xml, modhud / stem.upper())

    result["convertedExtras"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("official_assets", type=Path)
    parser.add_argument("merged_assets", type=Path)
    parser.add_argument("disc_game", type=Path)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()

    official = args.official_assets.resolve()
    merged = args.merged_assets.resolve()
    disc_game = args.disc_game.resolve()
    archives = [path.resolve() for path in args.archives]
    if not official.is_dir():
        raise SystemExit(f"official assets root not found: {official}")
    for archive in archives:
        if not archive.is_file():
            raise SystemExit(f"mod archive not found: {archive}")

    if merged.exists():
        shutil.rmtree(merged)
    shutil.copytree(official, merged)

    manifest: dict = {"mods": [], "fnfc": [], "nativeScripts": [], "extras": {}}
    extracted_roots: dict[str, Path] = {}
    with tempfile.TemporaryDirectory(prefix="fnf-ps2-mods-") as temp_name:
        temp = Path(temp_name)
        for index, archive in enumerate(archives):
            out = temp / f"mod{index:02d}"
            out.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive) as zf:
                safe_extract(zf, out)
            root = locate_mod_root(out)
            meta = metadata(root)
            mod_id = str(meta.get("id") or meta.get("title") or archive.stem)
            extracted_roots[mod_id] = root
            copied = merge_standard_assets(root, merged)
            manifest["mods"].append({
                "archive": archive.name,
                "id": mod_id,
                "title": meta.get("title", mod_id),
                "assetFilesMerged": copied,
            })
            # Scripts are intentionally represented by native C modules.
            if (root / "scripts").exists() or any(root.glob("*.hxc")):
                manifest["nativeScripts"].append(mod_id)

            fnfc = unpack_fnfcs_from_archive(archive, merged)
            manifest["fnfc"].extend(fnfc)

        manifest["extras"] = convert_extras(merged, extracted_roots, disc_game)

    if args.manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
