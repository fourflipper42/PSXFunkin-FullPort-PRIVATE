#!/usr/bin/env python3
"""Apply the validated Erect/Nightmare routing plus the first-note XA fix.

The routing body is pinned to the known-good pre-freeze-fix implementation so
this checkpoint cannot accidentally drift into later project work. After that
routing is applied, this wrapper makes two narrowly scoped runtime changes:

1. Same-channel Audio_ChannelXA calls become no-ops while XA is already playing.
2. Song start marks the already-selected full/vocal channel as active.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_ROUTING_COMMIT = "9acbd3c66bc032d3e25b68de16644c5a9ae02699"
BASE_ROUTING_PATH = "scripts/apply_erect_audio_routing.py"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: expected exactly one anchor, found {count}: {old[:100]!r}"
        )
    path.write_text(text.replace(old, new, 1))


def run_base_routing(root: Path) -> None:
    # actions/checkout uses a shallow checkout. Explicitly fetch the exact
    # known-good routing commit before extracting its script.
    subprocess.run(
        ["git", "fetch", "--no-tags", "--depth=1", "origin", BASE_ROUTING_COMMIT],
        check=True,
    )
    script = subprocess.check_output(
        ["git", "show", f"{BASE_ROUTING_COMMIT}:{BASE_ROUTING_PATH}"],
        text=True,
    )
    with tempfile.NamedTemporaryFile("w", suffix="-erect-routing.py", delete=False) as f:
        f.write(script)
        temp_path = Path(f.name)
    try:
        subprocess.run([sys.executable, str(temp_path), str(root)], check=True)
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, help="PSXFunkin source root")
    args = ap.parse_args()
    root = args.root

    run_base_routing(root)

    audio_c = root / "src" / "audio.c"
    stage_c = root / "src" / "stage.c"

    replace_once(
        audio_c,
        "void Audio_ChannelXA(u8 channel)\n"
        "{\n"
        "\t//Set XA filter to the given channel\n"
        "\tXA_SetFilter(channel);\n"
        "}",
        "void Audio_ChannelXA(u8 channel)\n"
        "{\n"
        "\t//Avoid resubmitting CdlSetfilter when the requested channel is\n"
        "\t//already active. The first opponent note otherwise re-filters the\n"
        "\t//new Erect XA stream to its current channel and can stall playback.\n"
        "\tif ((xa_state & XA_STATE_PLAYING) && xa_channel == channel)\n"
        "\t\treturn;\n"
        "\tXA_SetFilter(channel);\n"
        "}",
    )

    replace_once(
        stage_c,
        "\t\t\t\t\tAudio_PlayXA_File(&stage.music_file, 0x40, stage.music_channel, 0);\n"
        "\t\t\t\t\t\n"
        "\t\t\t\t\t//Wait until first sector has played",
        "\t\t\t\t\tAudio_PlayXA_File(&stage.music_file, 0x40, stage.music_channel, 0);\n"
        "\t\t\t\t\t//Playback begins on the full/vocal XA channel, so keep the\n"
        "\t\t\t\t\t//stage flag synchronized from the first audio sector.\n"
        "\t\t\t\t\tstage.flag |= STAGE_FLAG_VOCAL_ACTIVE;\n"
        "\t\t\t\t\t\n"
        "\t\t\t\t\t//Wait until first sector has played",
    )

    audio_text = audio_c.read_text()
    stage_text = stage_c.read_text()
    required = {
        audio_c: ["xa_channel == channel", "ERECT_BOPEEBO_SECTORS", "ERECT_UGH_SECTORS"],
        stage_c: [
            "Stage_SelectMusic",
            "stage.music_channel",
            "stage.flag |= STAGE_FLAG_VOCAL_ACTIVE;",
        ],
    }
    for path, needles in required.items():
        text = audio_text if path == audio_c else stage_text
        for needle in needles:
            if needle not in text:
                raise SystemExit(f"{path}: missing expected result {needle!r}")

    print("Applied Erect/Nightmare routing and first-opponent-note XA guard")


if __name__ == "__main__":
    main()
