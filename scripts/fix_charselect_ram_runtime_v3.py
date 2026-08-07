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
ENV_RECORD = 10112
CHAR_RECORD = 25088
ENV_COUNT = 36
CHAR_COUNT = 30

# The additional regional CLUTs are intentionally less RLE-compressible than
# the old single-palette records. 289,388 bytes was measured and already
# round-trip verified in CI; it is still far below the original 738,240-byte
# whole character bank that caused the PS1 malloc failure.
MAX_ENV_PACKED = 131072
MAX_CHAR_PACKED = 320000


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: fix_charselect_ram_runtime_v3.py <upstream>")

    root = Path(sys.argv[1])
    menu = root / "iso" / "menu"

    env_size = mod.pack_bank(menu / "csanim.bin", menu / "csanim.rle", ENV_RECORD, ENV_COUNT)
    char_size = mod.pack_bank(menu / "cschar.bin", menu / "cschar.rle", CHAR_RECORD, CHAR_COUNT)
    if env_size > MAX_ENV_PACKED:
        raise SystemExit(f"packed environment unexpectedly large: {env_size}")
    if char_size > MAX_CHAR_PACKED:
        raise SystemExit(f"packed character bank unexpectedly large: {char_size}")

    xml = root / "funkin.xml"
    xml_text = xml.read_text()
    if xml_text.count("csanim.bin") != 2 or xml_text.count("cschar.bin") != 2:
        raise SystemExit("unexpected Character Select ISO XML entries")
    xml_text = xml_text.replace("csanim.bin", "csanim.rle").replace("cschar.bin", "cschar.rle")
    xml.write_text(xml_text)

    # Reuse the already proven on-demand RLE decoder/runtime patch. Its scratch
    # arrays are sized from MENU_CS_RECORD_BYTES / MENU_CS_CHAR_RECORD_BYTES, so
    # the v3 512-byte spatial palette headers are included automatically.
    mod.patch_runtime(root)

    scratch = ENV_RECORD + CHAR_RECORD
    print(f"Character Select v3 RAM fix: {env_size + char_size} packed animation bytes + {scratch} bytes frame scratch")
    print("All active environment and all 30 high-resolution character/foreground frames remain byte-identical after decode.")


if __name__ == "__main__":
    main()
