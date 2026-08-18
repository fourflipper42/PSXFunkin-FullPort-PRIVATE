#!/usr/bin/env python3
"""Convert every current-format FNF song chart into the PS2 .CHT layout."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


def load_chartc(repo_root: Path):
    path = repo_root / "scripts" / "psxfunkin_chartc_v2.py"
    spec = importlib.util.spec_from_file_location("psxfunkin_chartc_v2", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_data_songs(root: Path) -> Path:
    candidates = [
        root / "data" / "songs",
        root / "assets" / "data" / "songs",
        root / "assets" / "shared" / "data" / "songs",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    for candidate in root.rglob("songs"):
        if candidate.is_dir() and candidate.parent.name == "data":
            return candidate
    raise FileNotFoundError(f"could not locate data/songs below {root}")


def variation_from_chart(song: str, chart_path: Path) -> str | None:
    stem = chart_path.stem
    prefix = f"{song}-chart"
    if not stem.lower().startswith(prefix.lower()):
        return None
    suffix = stem[len(prefix):]
    if not suffix:
        return "default"
    if suffix.startswith("-"):
        suffix = suffix[1:]
    return suffix or "default"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_root", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()

    chartc = load_chartc(args.repo_root.resolve())
    songs_root = find_data_songs(args.input_root.resolve())
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    failures: list[str] = []

    for song_dir in sorted(p for p in songs_root.iterdir() if p.is_dir()):
        song = song_dir.name
        for chart_path in sorted(song_dir.glob("*.json")):
            variation = variation_from_chart(song, chart_path)
            if variation is None:
                continue

            suffix = "" if variation == "default" else f"-{variation}"
            metadata_path = song_dir / f"{song}-metadata{suffix}.json"
            if not metadata_path.exists():
                failures.append(f"{song}/{variation}: missing {metadata_path.name}")
                continue

            try:
                chart = json.loads(chart_path.read_text(encoding="utf-8"))
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except Exception as exc:
                failures.append(f"{song}/{variation}: JSON error: {exc}")
                continue

            note_sets = chart.get("notes")
            if not isinstance(note_sets, dict):
                failures.append(f"{song}/{variation}: chart has no notes map")
                continue

            for difficulty in sorted(note_sets):
                if not isinstance(note_sets[difficulty], list):
                    continue
                try:
                    payload = chartc.convert(chart, metadata, difficulty)
                except Exception as exc:
                    failures.append(f"{song}/{variation}/{difficulty}: {exc}")
                    continue

                out = output_root / song / variation / f"{difficulty}.cht"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(payload)
                records.append(
                    {
                        "song": song,
                        "variation": variation,
                        "difficulty": difficulty,
                        "file": out.relative_to(output_root).as_posix(),
                        "bytes": len(payload),
                        "sha256": sha256(payload),
                    }
                )

    manifest = {
        "format": "PSXFunkin CHT / PS2 portable parser",
        "songs_root": songs_root.as_posix(),
        "count": len(records),
        "charts": records,
        "warnings": failures,
    }
    manifest_path = args.manifest or (output_root / "chart_manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"generated {len(records)} PS2 charts")
    if failures:
        print(f"warnings: {len(failures)}")
        for warning in failures:
            print(f"  {warning}")
    print(f"manifest: {manifest_path}")
    if not records:
        raise SystemExit("no charts were converted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
