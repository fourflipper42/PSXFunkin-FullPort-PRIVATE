#!/usr/bin/env python3
"""Apply the narrow Erect/Nightmare audio routing changes to PSXFunkin t0.12.

Run after patches/0001-current-difficulties.patch has been applied.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one anchor, found {count}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, help="PSXFunkin source root")
    args = ap.parse_args()
    root = args.root

    audio_h = root / "src" / "audio.h"
    audio_c = root / "src" / "audio.c"
    stage_h = root / "src" / "stage.h"
    stage_c = root / "src" / "stage.c"
    xml = root / "funkin.xml"

    replace_once(
        audio_h,
        "\tXA_ClwnB,  //CLWNB.XA\n\t\n\tXA_Max,",
        "\tXA_ClwnB,  //CLWNB.XA\n"
        "\tXA_ErectA, //ERECTA.XA\n"
        "\tXA_ErectB, //ERECTB.XA\n"
        "\tXA_ErectC, //ERECTC.XA\n"
        "\tXA_ErectD, //ERECTD.XA\n"
        "\t\n\tXA_Max,",
    )

    replace_once(
        audio_h,
        "\tXA_Hellclown,   //Hellclown\n\tXA_Expurgation, //Expurgation\n} XA_Track;",
        "\tXA_Hellclown,   //Hellclown\n"
        "\tXA_Expurgation, //Expurgation\n"
        "\t//ERECTA.XA\n"
        "\tXA_Erect_Bopeebo,\n"
        "\tXA_Erect_Fresh,\n"
        "\tXA_Erect_Dadbattle,\n"
        "\tXA_Erect_Spookeez,\n"
        "\t//ERECTB.XA\n"
        "\tXA_Erect_South,\n"
        "\tXA_Erect_Pico,\n"
        "\tXA_Erect_Philly,\n"
        "\tXA_Erect_Blammed,\n"
        "\t//ERECTC.XA\n"
        "\tXA_Erect_SatinPanties,\n"
        "\tXA_Erect_High,\n"
        "\tXA_Erect_Cocoa,\n"
        "\tXA_Erect_Eggnog,\n"
        "\t//ERECTD.XA\n"
        "\tXA_Erect_Senpai,\n"
        "\tXA_Erect_Roses,\n"
        "\tXA_Erect_Thorns,\n"
        "\tXA_Erect_Ugh,\n"
        "} XA_Track;",
    )

    replace_once(
        audio_c,
        '#include "main.h"\n',
        '#include "main.h"\n#include "erect_audio_generated.h"\n',
    )

    replace_once(
        audio_c,
        "\t{XA_ClwnB, XA_LENGTH(21886)}, //XA_Hellclown\n"
        "\t{XA_ClwnB, XA_LENGTH(19607)}, //XA_Expurgation\n};",
        "\t{XA_ClwnB, XA_LENGTH(21886)}, //XA_Hellclown\n"
        "\t{XA_ClwnB, XA_LENGTH(19607)}, //XA_Expurgation\n"
        "\t//ERECTA.XA\n"
        "\t{XA_ErectA, ERECT_BOPEEBO_SECTORS * IO_SECT_SIZE}, //XA_Erect_Bopeebo\n"
        "\t{XA_ErectA, ERECT_FRESH_SECTORS * IO_SECT_SIZE}, //XA_Erect_Fresh\n"
        "\t{XA_ErectA, ERECT_DADBATTLE_SECTORS * IO_SECT_SIZE}, //XA_Erect_Dadbattle\n"
        "\t{XA_ErectA, ERECT_SPOOKEEZ_SECTORS * IO_SECT_SIZE}, //XA_Erect_Spookeez\n"
        "\t//ERECTB.XA\n"
        "\t{XA_ErectB, ERECT_SOUTH_SECTORS * IO_SECT_SIZE}, //XA_Erect_South\n"
        "\t{XA_ErectB, ERECT_PICO_SECTORS * IO_SECT_SIZE}, //XA_Erect_Pico\n"
        "\t{XA_ErectB, ERECT_PHILLY_SECTORS * IO_SECT_SIZE}, //XA_Erect_Philly\n"
        "\t{XA_ErectB, ERECT_BLAMMED_SECTORS * IO_SECT_SIZE}, //XA_Erect_Blammed\n"
        "\t//ERECTC.XA\n"
        "\t{XA_ErectC, ERECT_SATINPANTIES_SECTORS * IO_SECT_SIZE}, //XA_Erect_SatinPanties\n"
        "\t{XA_ErectC, ERECT_HIGH_SECTORS * IO_SECT_SIZE}, //XA_Erect_High\n"
        "\t{XA_ErectC, ERECT_COCOA_SECTORS * IO_SECT_SIZE}, //XA_Erect_Cocoa\n"
        "\t{XA_ErectC, ERECT_EGGNOG_SECTORS * IO_SECT_SIZE}, //XA_Erect_Eggnog\n"
        "\t//ERECTD.XA\n"
        "\t{XA_ErectD, ERECT_SENPAI_SECTORS * IO_SECT_SIZE}, //XA_Erect_Senpai\n"
        "\t{XA_ErectD, ERECT_ROSES_SECTORS * IO_SECT_SIZE}, //XA_Erect_Roses\n"
        "\t{XA_ErectD, ERECT_THORNS_SECTORS * IO_SECT_SIZE}, //XA_Erect_Thorns\n"
        "\t{XA_ErectD, ERECT_UGH_SECTORS * IO_SECT_SIZE}, //XA_Erect_Ugh\n"
        "};",
    )

    replace_once(
        audio_c,
        '\t\t"\\\\MUSIC\\\\CLWNB.XA;1",  //XA_ClwnB\n\t};',
        '\t\t"\\\\MUSIC\\\\CLWNB.XA;1",  //XA_ClwnB\n'
        '\t\t"\\\\MUSIC\\\\ERECTA.XA;1", //XA_ErectA\n'
        '\t\t"\\\\MUSIC\\\\ERECTB.XA;1", //XA_ErectB\n'
        '\t\t"\\\\MUSIC\\\\ERECTC.XA;1", //XA_ErectC\n'
        '\t\t"\\\\MUSIC\\\\ERECTD.XA;1", //XA_ErectD\n'
        "\t};",
    )

    replace_once(
        audio_c,
        "void Audio_ChannelXA(u8 channel)\n"
        "{\n"
        "\t//Change CD filter\n"
        "\tXA_SetFilter(channel);\n"
        "}",
        "void Audio_ChannelXA(u8 channel)\n"
        "{\n"
        "\t//Do not submit a redundant CD filter command while the XA stream is\n"
        "\t//already playing on the requested channel. The first opponent note\n"
        "\t//otherwise re-filters the Erect stream to its already-active channel.\n"
        "\tif ((xa_state & XA_STATE_PLAYING) && xa_channel == channel)\n"
        "\t\treturn;\n"
        "\tXA_SetFilter(channel);\n"
        "}",
    )

    replace_once(
        stage_h,
        "\t//Music file\n\tCdlFILE music_file;",
        "\t//Music file\n\tCdlFILE music_file;\n\tu8 music_channel; //Effective channel; differs for Erect/Nightmare remixes",
    )

    helper = r'''Stage stage;

//Select the effective XA track/channel for the current difficulty.
//Erect and Nightmare share the official Erect remix audio; Nightmare keeps its own chart.
static void Stage_SelectMusic(XA_Track *track, u8 *channel)
{
	*track = (XA_Track)stage.stage_def->music_track;
	*channel = stage.stage_def->music_channel;

	if (stage.stage_diff != StageDiff_Erect && stage.stage_diff != StageDiff_Nightmare)
		return;

	switch (stage.stage_id)
	{
		case StageId_1_1: *track = XA_Erect_Bopeebo;       *channel = 0; break;
		case StageId_1_2: *track = XA_Erect_Fresh;         *channel = 2; break;
		case StageId_1_3: *track = XA_Erect_Dadbattle;     *channel = 4; break;
		case StageId_2_1: *track = XA_Erect_Spookeez;      *channel = 6; break;
		case StageId_2_2: *track = XA_Erect_South;         *channel = 0; break;
		case StageId_3_1: *track = XA_Erect_Pico;          *channel = 2; break;
		case StageId_3_2: *track = XA_Erect_Philly;        *channel = 4; break;
		case StageId_3_3: *track = XA_Erect_Blammed;       *channel = 6; break;
		case StageId_4_1: *track = XA_Erect_SatinPanties; *channel = 0; break;
		case StageId_4_2: *track = XA_Erect_High;          *channel = 2; break;
		case StageId_5_1: *track = XA_Erect_Cocoa;         *channel = 4; break;
		case StageId_5_2: *track = XA_Erect_Eggnog;        *channel = 6; break;
		case StageId_6_1: *track = XA_Erect_Senpai;        *channel = 0; break;
		case StageId_6_2: *track = XA_Erect_Roses;         *channel = 2; break;
		case StageId_6_3: *track = XA_Erect_Thorns;        *channel = 4; break;
		case StageId_7_1: *track = XA_Erect_Ugh;           *channel = 6; break;
		default: break; // Stage_SupportsDifficulty already prevents this path.
	}
}

//Stage music functions'''
    replace_once(stage_c, "Stage stage;\n\n//Stage music functions", helper)

    replace_once(stage_c, "Audio_ChannelXA(stage.stage_def->music_channel);", "Audio_ChannelXA(stage.music_channel);")
    replace_once(stage_c, "Audio_ChannelXA(stage.stage_def->music_channel + 1);", "Audio_ChannelXA(stage.music_channel + 1);")

    replace_once(
        stage_c,
        "void Stage_LoadMusic(void)\n{\n"
        "\t//Find music file and begin seeking to it\n"
        "\tAudio_GetXAFile(&stage.music_file, stage.stage_def->music_track);\n"
        "\tIO_SeekFile(&stage.music_file);",
        "void Stage_LoadMusic(void)\n{\n"
        "\t//Find the normal or Erect/Nightmare music file and begin seeking to it.\n"
        "\tXA_Track music_track;\n"
        "\tStage_SelectMusic(&music_track, &stage.music_channel);\n"
        "\tAudio_GetXAFile(&stage.music_file, music_track);\n"
        "\tIO_SeekFile(&stage.music_file);",
    )

    replace_once(
        stage_c,
        "Audio_PlayXA_File(&stage.music_file, 0x40, stage.stage_def->music_channel, 0);",
        "Audio_PlayXA_File(&stage.music_file, 0x40, stage.music_channel, 0);",
    )

    replace_once(
        stage_c,
        "\t\t\t\t\tAudio_PlayXA_File(&stage.music_file, 0x40, stage.music_channel, 0);\n"
        "\t\t\t\t\t\n"
        "\t\t\t\t\t//Wait until first sector has played",
        "\t\t\t\t\tAudio_PlayXA_File(&stage.music_file, 0x40, stage.music_channel, 0);\n"
        "\t\t\t\t\t//Playback starts on the full/vocal channel. Keep the stage\n"
        "\t\t\t\t\t//flag synchronized so the first opponent note does not send\n"
        "\t\t\t\t\t//a redundant CdlSetfilter command.\n"
        "\t\t\t\t\tstage.flag |= STAGE_FLAG_VOCAL_ACTIVE;\n"
        "\t\t\t\t\t\n"
        "\t\t\t\t\t//Wait until first sector has played",
    )

    replace_once(
        xml,
        '\t\t\t\t<file name = "clwnb.xa" type = "xa" source = "iso/music/clwnb.xa"/>\n'
        '\t\t\t\t<dummy sectors="128"/>\n\t\t\t</dir>',
        '\t\t\t\t<file name = "clwnb.xa" type = "xa" source = "iso/music/clwnb.xa"/>\n'
        '\t\t\t\t<dummy sectors="128"/>\n'
        '\t\t\t\t<file name = "erecta.xa" type = "xa" source = "iso/music/erecta.xa"/>\n'
        '\t\t\t\t<dummy sectors="128"/>\n'
        '\t\t\t\t<file name = "erectb.xa" type = "xa" source = "iso/music/erectb.xa"/>\n'
        '\t\t\t\t<dummy sectors="128"/>\n'
        '\t\t\t\t<file name = "erectc.xa" type = "xa" source = "iso/music/erectc.xa"/>\n'
        '\t\t\t\t<dummy sectors="128"/>\n'
        '\t\t\t\t<file name = "erectd.xa" type = "xa" source = "iso/music/erectd.xa"/>\n'
        '\t\t\t\t<dummy sectors="128"/>\n\t\t\t</dir>',
    )

    checks = {
        audio_h: ["XA_ErectA", "XA_Erect_Ugh"],
        audio_c: ["ERECT_BOPEEBO_SECTORS", "\\\\MUSIC\\\\ERECTD.XA;1", "xa_channel == channel"],
        stage_h: ["u8 music_channel"],
        stage_c: ["Stage_SelectMusic", "StageDiff_Nightmare", "stage.music_channel", "stage.flag |= STAGE_FLAG_VOCAL_ACTIVE;"],
        xml: ["erecta.xa", "erectd.xa"],
    }
    for path, needles in checks.items():
        text = path.read_text()
        for needle in needles:
            if needle not in text:
                raise SystemExit(f"{path}: missing expected result {needle!r}")

    print("Applied Erect/Nightmare audio routing and first-opponent-note freeze fix successfully")


if __name__ == "__main__":
    main()
