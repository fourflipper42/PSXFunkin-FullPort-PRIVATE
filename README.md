# PSXFunkin Full Port

PSXFunkin Full Port is an in-development PlayStation port project built on top of PSXFunkin. The goal is to bring the current Friday Night Funkin' content set to the original PlayStation while remaining compatible with real hardware and standard PS1 disc images.

## Status

This project is still under active development. Some content and systems are incomplete or undergoing compatibility work, and development builds should not be treated as final releases.

## Repository layout

- `scripts/` — asset conversion, chart conversion, source patching, and build-support tools.
- `scripts/ps1asset/` — PlayStation-oriented texture and archive utilities.
- `patches/` — source patches used by the build process.
- `sitecustomize.py` — Python compatibility support used by the tooling.

## Building

The build tooling targets the original PlayStation and produces MODE2/2352 BIN/CUE images. A complete reproducible public build workflow will be documented as the port approaches a stable release.

## Credits

- Friday Night Funkin' — Funkin' Crew and its contributors.
- PSXFunkin — cuckydev and contributors.
- Additional content and third-party assets remain credited to their respective creators.

This repository contains an unofficial fan port and is not affiliated with or endorsed by Sony Interactive Entertainment.
