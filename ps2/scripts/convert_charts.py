#!/usr/bin/env python3
"""Convert every current-format FNF song chart into PS2 gameplay assets."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
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
    parser.add_argument("--strict", action="store_true", help="Fail if any chart/event/note-kind stream cannot be converted")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    chartc = load_module(repo_root / "scripts" / "psxfunkin_chartc_v2.py", "psxfunkin_chartc_v2")
    eventc = load_module(Path(__file__).with_name("convert_events.py"), "convert_events")
    kindc = load_module(Path(__file__).with_name("convert_note_kinds.py"), "convert_note_kinds")
    songs_root = find_data_songs(args.input_root.resolve())
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    event_records: list[dict] = []
    kind_records: list[dict] = []
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

            try:
                event_payload, event_count = eventc.encode_events(chart)
                event_out = output_root / song / variation / "EVENTS.FEVT"
                event_out.parent.mkdir(parents=True, exist_ok=True)
                event_out.write_bytes(event_payload)
                event_records.append(
                    {
                        "song": song,
                        "variation": variation,
                        "file": event_out.relative_to(output_root).as_posix(),
                        "count": event_count,
                        "bytes": len(event_payload),
                        "sha256": sha256(event_payload),
                    }
                )
            except Exception as exc:
                failures.append(f"{song}/{variation}: event conversion error: {exc}")
                continue

            note_sets = chart.get("notes")
            if not isinstance(note_sets, dict):
                failures.append(f"{song}/{variation}: chart has no notes map")
                continue

            for difficulty in sorted(note_sets):
                if not isinstance(note_sets[difficulty], list):
                    continue
                try:
                    kind_ids, kind_payload = kindc.build(note_sets[difficulty])
                    payload = chartc.convert(
                        chart,
                        metadata,
                        difficulty,
                        note_kind_ids=kind_ids,
                    )
                except Exception as exc:
                    failures.append(f"{song}/{variation}/{difficulty}: {exc}")
                    continue

                out_dir = output_root / song / variation
                out_dir.mkdir(parents=True, exist_ok=True)
                out = out_dir / f"{difficulty}.cht"
                kind_out = out_dir / f"{difficulty}.fknd"
                out.write_bytes(payload)
                kind_out.write_bytes(kind_payload)
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
                kind_records.append(
                    {
                        "song": song,
                        "variation": variation,
                        "difficulty": difficulty,
                        "file": kind_out.relative_to(output_root).as_posix(),
                        "count": len(kind_ids),
                        "bytes": len(kind_payload),
                        "sha256": sha256(kind_payload),
                    }
                )

    manifest = {
        "format": "PSXFunkin CHT + FNF PS2 FEVT/FKND",
        "songs_root": songs_root.as_posix(),
        "count": len(records),
        "eventStreamCount": len(event_records),
        "noteKindStreamCount": len(kind_records),
        "charts": records,
        "eventStreams": event_records,
        "noteKindStreams": kind_records,
        "warnings": failures,
    }
    manifest_path = args.manifest or (output_root / "chart_manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"generated {len(records)} PS2 charts")
    print(f"generated {len(event_records)} PS2 event streams")
    print(f"generated {len(kind_records)} PS2 note-kind streams")
    if failures:
        print(f"warnings: {len(failures)}")
        for warning in failures:
            print(f"  {warning}")
    print(f"manifest: {manifest_path}")
    if not records:
        raise SystemExit("no charts were converted")
    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
