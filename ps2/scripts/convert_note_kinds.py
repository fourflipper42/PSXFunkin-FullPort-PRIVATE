#!/usr/bin/env python3
"""Encode per-chart FNF note kinds/params into compact FKND sidecars."""

from __future__ import annotations

import json
import struct
from typing import Any

MAGIC = b"FKND"
VERSION = 1
HEADER = struct.Struct("<4sHHII")
RECORD = struct.Struct("<II")


def canonical_params(note: dict[str, Any]) -> str:
    params = note.get("p")
    if params is None:
        params = note.get("params")
    if params is None:
        params = []
    return json.dumps(params, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def note_key(note: dict[str, Any]) -> tuple[str, str] | None:
    kind = str(note.get("k") or "").strip()
    if not kind:
        return None
    return kind, canonical_params(note)


def build_ids(notes: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    ids: dict[tuple[str, str], int] = {}
    for note in notes:
        key = note_key(note)
        if key is None or key in ids:
            continue
        index = len(ids) + 1
        if index > 0xFF:
            raise ValueError("chart uses more than 255 unique note-kind/parameter combinations")
        ids[key] = index
    return ids


def encode_ids(ids: dict[tuple[str, str], int]) -> bytes:
    if not ids:
        return HEADER.pack(MAGIC, VERSION, 0, RECORD.size, 0)

    ordered = sorted(ids.items(), key=lambda item: item[1])
    expected = list(range(1, len(ordered) + 1))
    if [index for _key, index in ordered] != expected:
        raise ValueError("note-kind IDs must be contiguous starting at 1")

    strings = bytearray()
    cache: dict[str, int] = {}
    records = bytearray()

    def add(value: str) -> int:
        if value in cache:
            return cache[value]
        offset = len(strings)
        strings.extend(value.encode("utf-8") + b"\0")
        cache[value] = offset
        return offset

    for (kind, params), _index in ordered:
        records.extend(RECORD.pack(add(kind), add(params)))

    return HEADER.pack(MAGIC, VERSION, len(ordered), RECORD.size, len(strings)) + records + strings


def build(notes: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], int], bytes]:
    ids = build_ids(notes)
    return ids, encode_ids(ids)
