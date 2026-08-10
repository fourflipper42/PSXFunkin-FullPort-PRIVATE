#!/usr/bin/env python3
"""Validate ISO9660 paths directly inside a raw MODE2/2352 PlayStation BIN."""
from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path

RAW_SECTOR = 2352
FORM1_DATA_OFFSET = 24
USER_DATA = 2048


@dataclass(frozen=True)
class Record:
    extent: int
    size: int
    flags: int
    name: str

    @property
    def is_dir(self) -> bool:
        return bool(self.flags & 0x02)


class RawIso9660:
    def __init__(self, path: Path):
        self.path = path
        self.fp = path.open("rb")
        pvd = self.sector(16)
        if pvd[0] != 1 or pvd[1:6] != b"CD001" or pvd[6] != 1:
            raise ValueError("sector 16 is not an ISO9660 primary volume descriptor")
        self.root = self._record(pvd, 156)
        if not self.root.is_dir:
            raise ValueError("PVD root record is not a directory")

    def close(self) -> None:
        self.fp.close()

    def sector(self, lba: int) -> bytes:
        self.fp.seek(lba * RAW_SECTOR + FORM1_DATA_OFFSET)
        data = self.fp.read(USER_DATA)
        if len(data) != USER_DATA:
            raise ValueError(f"short raw sector read at LBA {lba}")
        return data

    @staticmethod
    def _record(data: bytes, off: int) -> Record:
        length = data[off]
        if length < 34:
            raise ValueError(f"invalid ISO9660 directory record length {length}")
        name_len = data[off + 32]
        name_raw = data[off + 33 : off + 33 + name_len]
        if name_raw == b"\x00":
            name = "."
        elif name_raw == b"\x01":
            name = ".."
        else:
            name = name_raw.decode("ascii")
        return Record(
            extent=struct.unpack_from("<I", data, off + 2)[0],
            size=struct.unpack_from("<I", data, off + 10)[0],
            flags=data[off + 25],
            name=name,
        )

    def entries(self, directory: Record) -> list[Record]:
        if not directory.is_dir:
            raise ValueError(f"{directory.name} is not a directory")
        sectors = (directory.size + USER_DATA - 1) // USER_DATA
        out: list[Record] = []
        for index in range(sectors):
            data = self.sector(directory.extent + index)
            limit = min(USER_DATA, directory.size - index * USER_DATA)
            off = 0
            while off < limit:
                length = data[off]
                if length == 0:
                    break
                if length < 34 or off + length > limit:
                    raise ValueError(
                        f"malformed directory record in {directory.name} "
                        f"sector {index} offset {off}"
                    )
                out.append(self._record(data, off))
                off += length
        return out

    def find(self, path: str) -> Record:
        components = [p for p in path.replace("\\", "/").split("/") if p]
        if not components:
            return self.root
        current = self.root
        for index, wanted in enumerate(components):
            matches = [
                entry
                for entry in self.entries(current)
                if entry.name.upper() == wanted.upper()
            ]
            if not matches:
                raise FileNotFoundError(path)
            current = matches[0]
            if index != len(components) - 1 and not current.is_dir:
                raise FileNotFoundError(path)
        return current


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bin", type=Path)
    parser.add_argument("--require", action="append", default=[])
    parser.add_argument(
        "--require-multisector-dir",
        action="append",
        default=[],
        help="directory path that must span more than one 2048-byte ISO sector",
    )
    args = parser.parse_args()

    iso = RawIso9660(args.bin)
    try:
        for path in args.require:
            record = iso.find(path)
            if record.is_dir:
                raise SystemExit(f"required file is a directory: {path}")
            if record.size <= 0:
                raise SystemExit(f"required file is empty: {path}")
            print(f"FOUND {path} LBA={record.extent} SIZE={record.size}")

        for path in args.require_multisector_dir:
            record = iso.find(path)
            if not record.is_dir:
                raise SystemExit(f"required directory is a file: {path}")
            sectors = (record.size + USER_DATA - 1) // USER_DATA
            if sectors <= 1:
                raise SystemExit(
                    f"expected multi-sector directory {path}, got {record.size} bytes"
                )
            print(f"MULTISECTOR {path} BYTES={record.size} SECTORS={sectors}")
    finally:
        iso.close()

    print("RAW_PSX_ISO9660_VALIDATION_OK")


if __name__ == "__main__":
    main()
