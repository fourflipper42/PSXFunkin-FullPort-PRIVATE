#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, struct, subprocess
from pathlib import Path

MOVIES = [
    ('darnellCutscene.mp4', 'darnell.str', 'W1_DARNELL_FRAMES'),
    ('2hotCutscene.mp4', '2hot.str', 'W1_2HOT_FRAMES'),
    ('blazinCutscene.mp4', 'blazin.str', 'W1_BLAZIN_FRAMES'),
]
SECTOR = 2336
STR_MAGIC = b'\x60\x01\x01\x80'


def run(command):
    subprocess.run([str(item) for item in command], check=True, capture_output=False)


def encoded_frame_count(path: Path) -> int:
    data = path.read_bytes()
    maximum = 0
    if len(data) % SECTOR:
        raise RuntimeError(f'{path} is not 2336-byte sector aligned')
    for offset in range(0, len(data), SECTOR):
        sector = data[offset:offset + SECTOR]
        # XA subheader occupies the first 8 bytes. PSX STR video sectors use
        # real-time data submode 0x48; the MDEC header follows immediately.
        if sector[2] == 0x48 and sector[8:12] == STR_MAGIC:
            maximum = max(maximum, struct.unpack_from('<I', sector, 16)[0])
    if maximum <= 0:
        raise RuntimeError(f'no STR video frames found in {path}')
    return maximum


def patch_m1_v4_helper() -> None:
    # M1 v4 removes the two unguarded operations that previously happened before
    # PlayStr(): a redundant movie lookup and an infinite PADstart-release wait.
    # M1 v5 adds the VLC table initialization used by Sony's PsyQ CD movie
    # samples while leaving the already-proven lookup/stream/return path intact.
    # M1 v6 routes VLC decode through DecDCTvlc2 so that exact table is consumed
    # explicitly instead of relying on DecDCTvlc's internal/global table state.
    # M1 v7 matches Sony's CD/MOVIE samples by using CdlModeStream2 for STR reads.
    helper = Path(__file__).with_name('apply_iso9660_lookup_fallback.py')
    text = helper.read_text()
    validator_marker = 'M1 v4 redundant preflight ISO search survived'

    if 'M1_MOVIE_ENTRY_V4' not in text:
        start_marker = "    movie_play = r'''void Movie_Play("
        start = text.find(start_marker)
        if start < 0:
            raise RuntimeError('M1 v4 Movie_Play template start missing')
        end = text.find("\n'''", start + len(start_marker))
        if end < 0:
            raise RuntimeError('M1 v4 Movie_Play template end missing')
        end += len("\n'''")
        replacement = "\n".join([
            "    movie_play = r'''void Movie_Play(const char *path, unsigned long length)",
            "{",
            "\\tAudio_StopXA();",
            "",
            "\\t/* M1_MOVIE_ENTRY_V4",
            "\\t * Do not perform an unguarded preflight CdSearchFile/ISO scan here and do",
            "\\t * not spin waiting for PADstart. strDoPlayback owns bounded lookup/CD",
            "\\t * startup and reports E0-E4. Start is sampled only after playback begins. */",
            "\\tSTRFILE sfile;",
            "\\tstrcpy(sfile.FileName, path);",
            "\\tsfile.Xres = 320;",
            "\\tsfile.Yres = 240;",
            "\\tsfile.NumFrames = length;",
            "\\tPlayStr(320, 240, 0, 0, &sfile);",
            "",
            "\\tCdControlB(CdlPause, NULL, NULL);",
            "\\tDrawSync(0);",
            "\\tSetDispMask(1);",
            "}",
            "'''",
        ]).replace('\\t', '\t')
        text = text[:start] + replacement + text[end:]

    old_validation = (
        '    if "IO_SearchFile(&file, path)" not in movie:\n'
        '        raise SystemExit("Movie_Play does not use full ISO search")\n'
    )
    new_validation = (
        '    if "M1_MOVIE_ENTRY_V4" not in movie:\n'
        '        raise SystemExit("M1 v4 movie entry marker missing")\n'
        '    if "IO_SearchFile(&file, path)" in movie:\n'
        '        raise SystemExit("M1 v4 redundant preflight ISO search survived")\n'
        '    if "while (PadRead(1) & PADstart)" in movie:\n'
        '        raise SystemExit("M1 v4 unbounded Start-release wait survived")\n'
    )
    if old_validation in text:
        text = text.replace(old_validation, new_validation, 1)
    elif validator_marker not in text:
        raise RuntimeError('M1 v4 validator anchor missing')

    # Sony's PsyQ 4.4 CD/MOVIE samples declare a DECDCTTAB and call
    # DecDCTvlcBuild() before the first VLC decode. The inherited cuckydev
    # player omitted both. Install exactly that missing initialization.
    if 'M1_VLC_TABLE_V5' not in text:
        read_anchor = (
            '    strplay = root / "src/strplay.c"\n'
            '    text = strplay.read_text()\n'
        )
        read_patch = (
            '    strplay = root / "src/strplay.c"\n'
            '    text = strplay.read_text()\n'
            '    if "M1_VLC_TABLE_V5" not in text:\n'
            '        text = replace_once(\n'
            '            text,\n'
            '            "static STRENV strEnv;\\n",\n'
            '            "static STRENV strEnv;\\n\\n/* M1_VLC_TABLE_V5: Sony PsyQ libpress VLC table. */\\nstatic DECDCTTAB strVlcTable;\\n",\n'
            '            "M1 VLC table declaration",\n'
            '        )\n'
        )
        if text.count(read_anchor) != 1:
            raise RuntimeError(f'M1 v5 strplay read anchor changed: {text.count(read_anchor)}')
        text = text.replace(read_anchor, read_patch, 1)

        dct_anchor = (
            '\tDecDCTReset(0);\n'
            '\tDecDCToutCallback(strCallback);\n'
        )
        dct_patch = (
            '\tDecDCTReset(0);\n'
            '\t/* Sony PsyQ CD/MOVIE samples build this before the first VLC decode. */\n'
            '\tDecDCTvlcBuild(strVlcTable);\n'
            '\tDecDCToutCallback(strCallback);\n'
        )
        if text.count(dct_anchor) != 1:
            raise RuntimeError(f'M1 v5 MDEC init anchor changed: {text.count(dct_anchor)}')
        text = text.replace(dct_anchor, dct_patch, 1)

        validate_anchor = (
            '    if "M1_STR_DIAGNOSTIC_V3" not in strplay:\n'
            '        raise SystemExit("M1 v3 diagnostic STR player missing")\n'
        )
        validate_patch = (
            '    if "M1_STR_DIAGNOSTIC_V3" not in strplay:\n'
            '        raise SystemExit("M1 v3 diagnostic STR player missing")\n'
            '    if "M1_VLC_TABLE_V5" not in strplay or "DecDCTvlcBuild(strVlcTable);" not in strplay:\n'
            '        raise SystemExit("M1 v5 PsyQ VLC table initialization missing")\n'
        )
        if text.count(validate_anchor) != 1:
            raise RuntimeError(f'M1 v5 helper validator anchor changed: {text.count(validate_anchor)}')
        text = text.replace(validate_anchor, validate_patch, 1)

    # PsyQ provides an explicit-table decoder variant. Use it so the table built
    # above is definitely the one driving VLC expansion on every streamed frame.
    if 'M1_VLC_EXPLICIT_V6' not in text:
        vlc_anchor = '\tDecDCTvlc(next, strEnv->VlcBuff_ptr[strEnv->VlcID]);\n'
        vlc_patch = (
            '\t/* M1_VLC_EXPLICIT_V6: consume the built PsyQ table explicitly. */\n'
            '\tDecDCTvlc2(next, strEnv->VlcBuff_ptr[strEnv->VlcID], strVlcTable);\n'
        )
        if text.count(vlc_anchor) != 1:
            raise RuntimeError(f'M1 v6 VLC decode anchor changed: {text.count(vlc_anchor)}')
        text = text.replace(vlc_anchor, vlc_patch, 1)

        helper_validate_anchor = (
            '    if "M1_VLC_TABLE_V5" not in strplay or "DecDCTvlcBuild(strVlcTable);" not in strplay:\n'
            '        raise SystemExit("M1 v5 PsyQ VLC table initialization missing")\n'
        )
        helper_validate_patch = helper_validate_anchor + (
            '    if "M1_VLC_EXPLICIT_V6" not in strplay or "DecDCTvlc2(next, strEnv->VlcBuff_ptr[strEnv->VlcID], strVlcTable);" not in strplay:\n'
            '        raise SystemExit("M1 v6 explicit PsyQ VLC decoder missing")\n'
        )
        if text.count(helper_validate_anchor) != 1:
            raise RuntimeError(f'M1 v6 helper validator anchor changed: {text.count(helper_validate_anchor)}')
        text = text.replace(helper_validate_anchor, helper_validate_patch, 1)

    # Sony's PsyQ 4.4 CD/MOVIE samples start STR streaming with Stream2. The
    # inherited player used Stream, which v6 showed can deliver intermittent
    # decodable data but not a stable movie stream. Match Sony's command exactly.
    if 'M1_STREAM2_V7' not in text:
        stream_anchor = 'if (CdRead2(CdlModeStream | CdlModeSpeed | CdlModeRT) != 0)\n'
        stream_patch = (
            '/* M1_STREAM2_V7: Sony PsyQ CD/MOVIE streaming mode. */\n'
            '\t\tif (CdRead2(CdlModeStream2 | CdlModeSpeed | CdlModeRT) != 0)\n'
        )
        if text.count(stream_anchor) != 1:
            raise RuntimeError(f'M1 v7 CD stream anchor changed: {text.count(stream_anchor)}')
        text = text.replace('\t\t' + stream_anchor, '\t\t' + stream_patch, 1)

        helper_v6_anchor = (
            '    if "M1_VLC_EXPLICIT_V6" not in strplay or "DecDCTvlc2(next, strEnv->VlcBuff_ptr[strEnv->VlcID], strVlcTable);" not in strplay:\n'
            '        raise SystemExit("M1 v6 explicit PsyQ VLC decoder missing")\n'
        )
        helper_v7_patch = helper_v6_anchor + (
            '    if "M1_STREAM2_V7" not in strplay or "CdlModeStream2 | CdlModeSpeed | CdlModeRT" not in strplay:\n'
            '        raise SystemExit("M1 v7 Sony Stream2 mode missing")\n'
        )
        if text.count(helper_v6_anchor) != 1:
            raise RuntimeError(f'M1 v7 helper validator anchor changed: {text.count(helper_v6_anchor)}')
        text = text.replace(helper_v6_anchor, helper_v7_patch, 1)

    helper.write_text(text)

    # build_pico_mix_movies.py injects the final post-apply validator into the
    # Pico apply script. Keep its v4 movie-entry contract aligned and extend it
    # to require the v5/v6 VLC decode contract in the final generated tree.
    pico_builder = Path(__file__).with_name('build_pico_mix_movies.py')
    pico = pico_builder.read_text()
    old_key = '            "Movie resolver": "IO_SearchFile(&file, path)",'
    new_key = '            "Movie entry v4": "M1_MOVIE_ENTRY_V4",'
    if old_key in pico:
        pico = pico.replace(old_key, new_key, 1)

    old_guard = (
        '        if _runtime_required["Movie resolver"] not in _runtime_movie:\n'
        '            _pico_fail("M1/M3 validation", "Movie_Play is not using the shared resolver")\n'
    )
    new_guard = (
        '        if _runtime_required["Movie entry v4"] not in _runtime_movie:\n'
        '            _pico_fail("M1/M3 validation", "M1 v4 movie entry marker missing")\n'
        '        if "IO_SearchFile(&file, path)" in _runtime_movie:\n'
        '            _pico_fail("M1/M3 validation", "M1 v4 redundant preflight ISO search survived")\n'
        '        if "while (PadRead(1) & PADstart)" in _runtime_movie:\n'
        '            _pico_fail("M1/M3 validation", "M1 v4 unbounded Start-release wait survived")\n'
    )
    if old_guard in pico:
        pico = pico.replace(old_guard, new_guard, 1)
    elif 'M1 v4 redundant preflight ISO search survived' not in pico:
        raise RuntimeError('M1 v4 Pico validator anchor missing')

    if 'M1 v5 PsyQ VLC table initialization missing' not in pico:
        runtime_anchor = (
            '        if _runtime_required["STR resolver"] not in _runtime_str:\n'
            '            _pico_fail("M1/M3 validation", "STR player is not using the shared resolver")\n'
        )
        runtime_patch = (
            '        if _runtime_required["STR resolver"] not in _runtime_str:\n'
            '            _pico_fail("M1/M3 validation", "STR player is not using the shared resolver")\n'
            '        if "M1_VLC_TABLE_V5" not in _runtime_str or "DecDCTvlcBuild(strVlcTable);" not in _runtime_str:\n'
            '            _pico_fail("M1/M3 validation", "M1 v5 PsyQ VLC table initialization missing")\n'
        )
        if pico.count(runtime_anchor) != 1:
            raise RuntimeError(f'M1 v5 Pico runtime validator anchor changed: {pico.count(runtime_anchor)}')
        pico = pico.replace(runtime_anchor, runtime_patch, 1)

    if 'M1 v6 explicit PsyQ VLC decoder missing' not in pico:
        runtime_v5_anchor = (
            '        if "M1_VLC_TABLE_V5" not in _runtime_str or "DecDCTvlcBuild(strVlcTable);" not in _runtime_str:\n'
            '            _pico_fail("M1/M3 validation", "M1 v5 PsyQ VLC table initialization missing")\n'
        )
        runtime_v6_patch = runtime_v5_anchor + (
            '        if "M1_VLC_EXPLICIT_V6" not in _runtime_str or "DecDCTvlc2(next, strEnv->VlcBuff_ptr[strEnv->VlcID], strVlcTable);" not in _runtime_str:\n'
            '            _pico_fail("M1/M3 validation", "M1 v6 explicit PsyQ VLC decoder missing")\n'
        )
        if pico.count(runtime_v5_anchor) != 1:
            raise RuntimeError(f'M1 v6 Pico runtime validator anchor changed: {pico.count(runtime_v5_anchor)}')
        pico = pico.replace(runtime_v5_anchor, runtime_v6_patch, 1)

    if 'M1 v7 Sony Stream2 mode missing' not in pico:
        runtime_v6_anchor = (
            '        if "M1_VLC_EXPLICIT_V6" not in _runtime_str or "DecDCTvlc2(next, strEnv->VlcBuff_ptr[strEnv->VlcID], strVlcTable);" not in _runtime_str:\n'
            '            _pico_fail("M1/M3 validation", "M1 v6 explicit PsyQ VLC decoder missing")\n'
        )
        runtime_v7_patch = runtime_v6_anchor + (
            '        if "M1_STREAM2_V7" not in _runtime_str or "CdlModeStream2 | CdlModeSpeed | CdlModeRT" not in _runtime_str:\n'
            '            _pico_fail("M1/M3 validation", "M1 v7 Sony Stream2 mode missing")\n'
        )
        if pico.count(runtime_v6_anchor) != 1:
            raise RuntimeError(f'M1 v7 Pico runtime validator anchor changed: {pico.count(runtime_v6_anchor)}')
        pico = pico.replace(runtime_v6_anchor, runtime_v7_patch, 1)
    pico_builder.write_text(pico)

    # Temporary M1 acceptance build: patch the generated Pico apply step so the
    # final runtime tree boots directly through one known-good STR before any
    # Weekend/SP story state. After Movie_Play returns, normal menu startup is
    # untouched. This keeps the large-disc lookup conditions while isolating the
    # generic movie subsystem for emulator/hardware testing.
    pico_apply = Path(__file__).with_name('apply_pico_mixes_v1.py')
    apply_text = pico_apply.read_text()
    diag_marker = 'M1_ISOLATED_STR_BOOT_SCRIPT_V1'
    if diag_marker not in apply_text:
        diag_anchor = '    print("Applied all 15 official Pico Mixes, Pico Freeplay routing, runtime events, and ISO9660 lookup fallback")\n'
        if apply_text.count(diag_anchor) != 1:
            raise RuntimeError(f'M1 diagnostic apply anchor changed: {apply_text.count(diag_anchor)}')
        diag_insert = r'''    # M1_ISOLATED_STR_BOOT_SCRIPT_V1
    diag_header = root / "src/pico_mix_movies_generated.h"
    frame_prefix = "#define PICO_STRESS_INTRO_FRAMES "
    frame_lines = [line for line in diag_header.read_text().splitlines() if line.startswith(frame_prefix)]
    if len(frame_lines) != 1:
        raise SystemExit(f"M1 diagnostic frame macro count changed: {len(frame_lines)}")
    diag_frames = int(frame_lines[0][len(frame_prefix):].strip())

    diag_main_path = root / "src/main.c"
    diag_main = diag_main_path.read_text()
    if "M1_ISOLATED_STR_BOOT_V1" not in diag_main:
        if '#include "movie.h"\n' not in diag_main:
            diag_main = once(
                diag_main,
                '#include "stage.h"\n',
                '#include "stage.h"\n#include "movie.h"\n',
                "M1 diagnostic movie include",
            )
        timer_anchor = "\tTimer_Init();\n\t\n\t//Start game"
        timer_patch = (
            "\tTimer_Init();\n"
            "\n"
            "\t/* M1_ISOLATED_STR_BOOT_V1: direct generic STR acceptance test. */\n"
            f'\tMovie_Play("\\\\MOVIE\\\\PSTRS.STR;1", {diag_frames});\n'
            "\n"
            "\t//Start game"
        )
        diag_main = once(diag_main, timer_anchor, timer_patch, "M1 diagnostic boot hook")
        diag_main_path.write_text(diag_main)

'''
        apply_text = apply_text.replace(diag_anchor, diag_insert + diag_anchor, 1)
        pico_apply.write_text(apply_text)

    print('M1 v7: explicit Sony VLC-table decode, Stream2 CD mode, and isolated STR boot diagnostic installed')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--psxavenc', type=Path, required=True)
    parser.add_argument('--ffprobe', default='ffprobe')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--header', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    report = []
    defines = []
    patch_m1_v4_helper()
    for srcname, outname, define in MOVIES:
        source = args.root / 'videos/videos' / srcname
        out = args.out / outname
        run([
            args.psxavenc, '-q', '-t', 'str', '-v', 'v2', '-f', '37800',
            '-b', '4', '-c', '2', '-s', '320x240', '-r', '15', '-x', '2',
            source, out,
        ])
        frames = encoded_frame_count(out)
        duration = float(subprocess.run([
            str(args.ffprobe), '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=nw=1:nk=1', str(source),
        ], check=True, text=True, capture_output=True).stdout.strip())
        report.append({
            'source': srcname,
            'file': outname,
            'frames': frames,
            'source_duration': duration,
            'bytes': out.stat().st_size,
            'sector_size': SECTOR,
        })
        defines.append(f'#define {define} {frames}')

    args.header.parent.mkdir(parents=True, exist_ok=True)
    args.header.write_text(
        '#ifndef _WEEKEND1_MOVIES_GENERATED_H\n'
        '#define _WEEKEND1_MOVIES_GENERATED_H\n'
        + '\n'.join(defines)
        + '\n#endif\n'
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
