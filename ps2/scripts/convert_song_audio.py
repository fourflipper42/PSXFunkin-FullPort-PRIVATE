#!/usr/bin/env python3
"""Convert official FNF song audio into PS2-friendly PCM per song variation.

Modern FNF may select `Inst-<instrumental>.ogg` and character/variation-specific
`Voices-*.ogg` stems. This mirrors the game's resolution rules at build time,
then emits exactly one Inst stream and one already-combined Voices stream for
each metadata variation. The PS2 therefore gets simple, sample-accurate PCM
without accidentally mixing unrelated Pico/Erect/etc. vocal files together.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

RATE = 48_000
CHANNELS = 2
BITS = 16
FRAME_BYTES = CHANNELS * (BITS // 8)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ffmpeg_base(ffmpeg: str) -> list[str]:
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]


def convert_one(ffmpeg: str, src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(
        ffmpeg_base(ffmpeg)
        + [
            "-i", str(src),
            "-vn",
            "-ar", str(RATE),
            "-ac", str(CHANNELS),
            "-f", "s16le",
            str(dst),
        ]
    )


def convert_vocals(ffmpeg: str, stems: list[Path], dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if len(stems) == 1:
        convert_one(ffmpeg, stems[0], dst)
        return

    cmd = ffmpeg_base(ffmpeg)
    for stem in stems:
        cmd += ["-i", str(stem)]
    inputs = "".join(f"[{i}:a]" for i in range(len(stems)))
    filt = f"{inputs}amix=inputs={len(stems)}:duration=longest:normalize=0[v]"
    cmd += [
        "-filter_complex", filt,
        "-map", "[v]",
        "-ar", str(RATE),
        "-ac", str(CHANNELS),
        "-f", "s16le",
        str(dst),
    ]
    run(cmd)


def find_case_insensitive(directory: Path, exact_name: str) -> Path | None:
    if not directory.is_dir():
        return None
    target = exact_name.lower()
    for child in directory.iterdir():
        if child.is_file() and child.name.lower() == target:
            return child
    return None


def find_child_dir_case_insensitive(directory: Path, name: str) -> Path | None:
    if not directory.is_dir():
        return None
    target = name.lower()
    for child in directory.iterdir():
        if child.is_dir() and child.name.lower() == target:
            return child
    return None


def find_assets_roots(root: Path) -> tuple[Path, Path]:
    root = root.resolve()
    candidates = [root, root / "assets"]
    for assets in candidates:
        songs_audio = assets / "songs"
        songs_data = assets / "data" / "songs"
        if songs_audio.is_dir() and songs_data.is_dir():
            return songs_audio, songs_data
    raise FileNotFoundError(f"could not locate assets/songs and assets/data/songs below {root}")


def metadata_variation(song_id: str, metadata_path: Path) -> str | None:
    stem = metadata_path.stem
    prefix = f"{song_id}-metadata"
    if not stem.lower().startswith(prefix.lower()):
        return None
    suffix = stem[len(prefix):]
    if not suffix:
        return "default"
    if suffix.startswith("-"):
        suffix = suffix[1:]
    return suffix or "default"


def reduce_character_ids(character_id: str) -> list[str]:
    parts = [part for part in character_id.split("-") if part]
    result: list[str] = []
    while parts:
        result.append("-".join(parts))
        parts.pop()
    return result


def resolve_voice(directory: Path, character_id: str, variation: str) -> Path | None:
    suffix = "" if variation == "default" else f"-{variation}"
    ids = reduce_character_ids(character_id)

    for char_id in ids:
        found = find_case_insensitive(directory, f"Voices-{char_id}{suffix}.ogg")
        if found is not None:
            return found

    if suffix:
        for char_id in ids:
            found = find_case_insensitive(directory, f"Voices-{char_id}.ogg")
            if found is not None:
                return found
    return None


def explicit_voice_list(
    directory: Path,
    ids: object,
    variation: str,
) -> list[Path] | None:
    if not isinstance(ids, list) or not ids:
        return None
    suffix = "" if variation == "default" else f"-{variation}"
    resolved: list[Path] = []
    for raw_id in ids:
        voice_id = str(raw_id)
        path = find_case_insensitive(directory, f"Voices-{voice_id}{suffix}.ogg")
        if path is None:
            return None
        resolved.append(path)
    return resolved


def dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def resolve_vocals(directory: Path, characters: dict, variation: str) -> list[Path]:
    stems: list[Path] = []

    player_explicit = explicit_voice_list(directory, characters.get("playerVocals"), variation)
    if player_explicit is not None:
        stems.extend(player_explicit)
    else:
        player = str(characters.get("player") or "")
        if player:
            voice = resolve_voice(directory, player, variation)
            if voice is not None:
                stems.append(voice)

    opponent_explicit = explicit_voice_list(directory, characters.get("opponentVocals"), variation)
    if opponent_explicit is not None:
        stems.extend(opponent_explicit)
    else:
        opponent = str(characters.get("opponent") or "")
        if opponent:
            voice = resolve_voice(directory, opponent, variation)
            if voice is not None:
                stems.append(voice)

    stems = dedupe_paths(stems)
    if stems:
        return stems

    suffix = "" if variation == "default" else f"-{variation}"
    legacy = find_case_insensitive(directory, f"Voices{suffix}.ogg")
    if legacy is None and suffix:
        legacy = find_case_insensitive(directory, "Voices.ogg")
    return [legacy] if legacy is not None else []


def resolve_instrumental(directory: Path, characters: dict) -> Path | None:
    instrumental = str(characters.get("instrumental") or "")
    if instrumental:
        selected = find_case_insensitive(directory, f"Inst-{instrumental}.ogg")
        if selected is not None:
            return selected
    return find_case_insensitive(directory, "Inst.ogg")


def describe_pcm(path: Path | None) -> dict | None:
    if path is None or not path.exists():
        return None
    size = path.stat().st_size
    frames = size // FRAME_BYTES
    return {"bytes": size, "frames": frames, "seconds": frames / RATE}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("assets_root", type=Path, help="Official FNF assets root (or parent containing assets/)")
    parser.add_argument("output_root", type=Path, help="PS2 audio output root")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()

    ffmpeg = shutil.which(args.ffmpeg) if Path(args.ffmpeg).name == args.ffmpeg else args.ffmpeg
    if not ffmpeg or not Path(ffmpeg).exists():
        raise SystemExit(f"ffmpeg not found: {args.ffmpeg}")

    songs_audio_root, songs_data_root = find_assets_roots(args.assets_root)
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "format": {
            "sample_rate": RATE,
            "channels": CHANNELS,
            "bits": BITS,
            "frame_bytes": FRAME_BYTES,
            "encoding": "signed 16-bit little-endian PCM",
        },
        "variations": [],
        "warnings": [],
    }

    for data_dir in sorted(p for p in songs_data_root.iterdir() if p.is_dir()):
        song_id = data_dir.name
        audio_dir = find_child_dir_case_insensitive(songs_audio_root, song_id)
        if audio_dir is None:
            manifest["warnings"].append(f"{song_id}: missing audio directory")
            continue

        metadata_paths = sorted(
            p for p in data_dir.glob("*.json") if "metadata" in p.stem.lower()
        )
        for metadata_path in metadata_paths:
            variation = metadata_variation(song_id, metadata_path)
            if variation is None:
                continue
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except Exception as exc:
                manifest["warnings"].append(f"{song_id}/{variation}: metadata error: {exc}")
                continue

            play = metadata.get("playData") or {}
            characters = play.get("characters") or {}
            inst_src = resolve_instrumental(audio_dir, characters)
            if inst_src is None:
                manifest["warnings"].append(f"{song_id}/{variation}: no instrumental found")
                continue
            vocal_srcs = resolve_vocals(audio_dir, characters, variation)

            out_dir = output_root / song_id / variation
            inst_dst = out_dir / "INST.PCM"
            voices_dst = out_dir / "VOICES.PCM" if vocal_srcs else None

            print(f"[PS2 audio] {song_id}/{variation}")
            print(f"  inst: {inst_src.name}")
            print(f"  voices: {', '.join(p.name for p in vocal_srcs) if vocal_srcs else '(none)'}")
            convert_one(ffmpeg, inst_src, inst_dst)
            if voices_dst is not None:
                convert_vocals(ffmpeg, vocal_srcs, voices_dst)

            manifest["variations"].append(
                {
                    "song": song_id,
                    "variation": variation,
                    "instrumental_id": str(characters.get("instrumental") or ""),
                    "inst": inst_dst.relative_to(output_root).as_posix(),
                    "voices": voices_dst.relative_to(output_root).as_posix() if voices_dst else None,
                    "source_inst": inst_src.name,
                    "source_vocal_stems": [path.name for path in vocal_srcs],
                    "inst_info": describe_pcm(inst_dst),
                    "voices_info": describe_pcm(voices_dst),
                }
            )

    manifest_path = args.manifest or (output_root / "AUDIOIDX.JSON")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"converted {len(manifest['variations'])} song variations")
    print(f"warnings: {len(manifest['warnings'])}")
    print(f"manifest: {manifest_path}")
    if not manifest["variations"]:
        raise SystemExit("no song variations were converted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
