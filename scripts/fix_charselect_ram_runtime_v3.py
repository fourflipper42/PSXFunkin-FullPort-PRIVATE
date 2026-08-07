#!/usr/bin/env python3
"""Run the proven lossless Character Select RLE loader with v3 record sizes."""
from pathlib import Path
import importlib.util
import sys

here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("csram_base", here / "fix_charselect_ram_runtime.py")
if spec is None or spec.loader is None:
    raise SystemExit("cannot load base Character Select RAM packer")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# v3 keeps exactly the same 4bpp pixel payloads and adds 15 extra 32-byte
# palettes per frame: 9632 + 480 = 10112; 24608 + 480 = 25088.
mod.ENV_RECORD = 10112
mod.CHAR_RECORD = 25088

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: fix_charselect_ram_runtime_v3.py <upstream>")
    mod.main()
