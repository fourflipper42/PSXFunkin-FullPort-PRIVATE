#!/usr/bin/env python3
"""Fix the first-opponent-note XA filter stall.

PSXFunkin starts song playback on the full/vocal XA channel, but its stage flag
is initially clear. The first opponent note therefore sends a redundant
CdlSetfilter command to the channel that is already active. With the new Erect
XA streams this can stall the CD command path. Mark vocals active when playback
starts and make later same-channel Audio_ChannelXA calls no-ops.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one anchor, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    args = ap.parse_args()

    audio_c = args.root / "src" / "audio.c"
    stage_c = args.root / "src" / "stage.c"

    replace_once(
        audio_c,
        "void Audio_ChannelXA(u8 channel)\n"
        "{\n"
        "\t//Change CD filter\n"
        "\tXA_SetFilter(channel);\n"
        "}",
        "void Audio_ChannelXA(u8 channel)\n"
        "{\n"
        "\t//Do not submit a redundant CD filter command while the stream is\n"
        "\t//already playing on this channel. This is especially important for\n"
        "\t//the densely interleaved Erect XA files.\n"
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
        "\t\t\t\t\t//Playback begins on the full/vocal channel. Keep the stage\n"
        "\t\t\t\t\t//state synchronized so the first opponent note does not issue\n"
        "\t\t\t\t\t//a redundant CdlSetfilter command.\n"
        "\t\t\t\t\tstage.flag |= STAGE_FLAG_VOCAL_ACTIVE;\n"
        "\t\t\t\t\t\n"
        "\t\t\t\t\t//Wait until first sector has played",
    )

    audio_text = audio_c.read_text()
    stage_text = stage_c.read_text()
    if "xa_channel == channel" not in audio_text:
        raise SystemExit("Audio same-channel guard was not applied")
    if "stage.flag |= STAGE_FLAG_VOCAL_ACTIVE;" not in stage_text:
        raise SystemExit("Stage vocal-active initialization was not applied")

    print("Applied first-opponent-note XA filter freeze fix")


if __name__ == "__main__":
    main()
