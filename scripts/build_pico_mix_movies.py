#!/usr/bin/env python3
"""Convert the official Stress Pico Mix opening and ending cutscenes to PS1 STR."""
from __future__ import annotations

import argparse
import json
import math
import struct
import subprocess
import tempfile
import traceback
from pathlib import Path

from PIL import Image

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "ps1asset"))
from animateatlas_flatten import AnimateAtlas, render_leaves

SECTOR = 2336
STR_MAGIC = b"\x60\x01\x01\x80"
FPS = 15


def workflow_escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def phase(message: str) -> None:
    print(f"[Pico Mix movie] {message}", flush=True)


def run_checked(command: list[str], label: str) -> str:
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output = (result.stdout or "").strip()
    if result.returncode != 0:
        short = output[-3000:] if output else "no diagnostic output"
        print(f"::error title={workflow_escape(label)}::{workflow_escape(short)}", flush=True)
        raise RuntimeError(f"{label} failed with exit code {result.returncode}\n{output[-12000:]}")
    return output


def encoded_frame_count(path: Path) -> int:
    data = path.read_bytes()
    if len(data) % SECTOR:
        raise RuntimeError(f"{path} is not 2336-byte sector aligned")
    maximum = 0
    for offset in range(0, len(data), SECTOR):
        sector = data[offset:offset + SECTOR]
        if sector[2] == 0x48 and sector[8:12] == STR_MAGIC:
            maximum = max(maximum, struct.unpack_from("<I", sector, 16)[0])
    if maximum <= 0:
        raise RuntimeError(f"no STR frames found in {path}")
    return maximum


def probe_video(source: Path, ffmpeg: Path) -> dict[str, str]:
    ffprobe = ffmpeg.with_name("ffprobe") if ffmpeg.parent != Path(".") else Path("ffprobe")
    result = subprocess.run([
        str(ffprobe), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,pix_fmt,color_range,color_space,color_transfer,color_primaries",
        "-of", "json", str(source),
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for generated Pico ending: {result.stdout}")
    streams = json.loads(result.stdout).get("streams") or []
    if len(streams) != 1:
        raise RuntimeError(f"generated Pico ending has {len(streams)} video streams")
    stream = streams[0]
    if stream.get("color_space") not in {"bt470bg", "smpte170m"}:
        raise RuntimeError(f"generated Pico ending has unsafe colorspace for psxavenc: {stream}")
    phase(
        "ending video metadata verified: "
        f"codec={stream.get('codec_name')} pix_fmt={stream.get('pix_fmt')} "
        f"colorspace={stream.get('color_space')} range={stream.get('color_range')}"
    )
    return stream


def build_ending(atlas_path: Path, audio: Path, ffmpeg: Path, temporary: Path) -> tuple[Path, dict[str, str]]:
    phase("ending atlas render started")
    atlas = AnimateAtlas(atlas_path)
    atlas_frames = atlas.timeline_length(atlas.root["TL"])
    frame_count = math.ceil((320 / 24) * FPS)

    silent = temporary / "stress-pico-ending-silent.mp4"
    process = subprocess.Popen([
        str(ffmpeg), "-y", "-loglevel", "error", "-f", "rawvideo",
        "-pix_fmt", "rgb24", "-s", "320x240", "-r", str(FPS), "-i", "-",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", str(FPS), "-bf", "0",
        "-colorspace", "bt470bg", "-color_primaries", "smpte170m",
        "-color_trc", "smpte170m", "-color_range", "tv",
        "-movflags", "+faststart", str(silent),
    ], stdin=subprocess.PIPE)
    assert process.stdin is not None
    for output_frame in range(frame_count):
        source_frame = min(atlas_frames - 1, math.floor(output_frame * 24 / FPS))
        sprite, _ = render_leaves(atlas.leaves_for_frame(source_frame))
        sprite = sprite.convert("RGBA")
        scale = min(310 / max(1, sprite.width), 225 / max(1, sprite.height))
        sprite = sprite.resize(
            (max(1, round(sprite.width * scale)), max(1, round(sprite.height * scale))),
            Image.Resampling.LANCZOS,
        )
        frame = Image.new("RGBA", (320, 240), "black")
        frame.alpha_composite(sprite, ((320 - sprite.width) // 2, (240 - sprite.height) // 2))
        fade_start = math.floor((270 / 24) * FPS)
        if output_frame >= fade_start:
            alpha = min(1.0, (output_frame - fade_start) / max(1, frame_count - fade_start))
            frame = Image.blend(frame.convert("RGB"), Image.new("RGB", frame.size, "black"), alpha).convert("RGBA")
        process.stdin.write(frame.convert("RGB").tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg failed while rendering Stress Pico ending")
    phase("ending atlas render completed")

    target = temporary / "stress-pico-ending.mp4"
    phase("ending audio normalization and mux started")
    run_checked([
        str(ffmpeg), "-y", "-loglevel", "error", "-fflags", "+genpts",
        "-i", str(silent), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-af", "aresample=44100:async=1:first_pts=0,asetpts=N/SR/TB",
        "-avoid_negative_ts", "make_zero", "-t", f"{frame_count / FPS:.6f}",
        "-movflags", "+faststart", str(target),
    ], "Pico ending audio mux")
    phase("ending audio normalization and mux completed")
    return target, probe_video(target, ffmpeg)


def install_post_apply_guard() -> None:
    target = Path(__file__).resolve().with_name("apply_pico_mixes_v1.py")
    marker = "# PICO_CI_POST_APPLY_GUARD_V4"
    source = target.read_text()
    if marker in source:
        return
    guard = r'''

# PICO_CI_POST_APPLY_GUARD_V4
if __name__ == "__main__":
    import json as _pico_json
    import re as _pico_re
    import subprocess as _pico_subprocess
    import sys as _pico_sys
    import traceback as _pico_traceback
    from pathlib import Path as _PicoPath

    def _pico_escape(value):
        return str(value).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")

    def _pico_fail(title, detail):
        print("::error title=" + _pico_escape(title) + "::" + _pico_escape(detail), flush=True)
        _pico_sys.exit(1)

    _pico_args = _pico_sys.argv[1:]
    try:
        _pico_index = _pico_args.index("--upstream")
        _pico_root = _PicoPath(_pico_args[_pico_index + 1])
    except (ValueError, IndexError):
        _pico_root = None

    if _pico_root is not None:
        _pico_stagedef_path = _pico_root / "src/stagedef_disc1.h"
        _pico_stagedef = _pico_stagedef_path.read_text()
        _pico_expected_speed = "{FIXED_DEC(25,10),FIXED_DEC(29,10),FIXED_DEC(32,10)}"
        _pico_stress = _pico_re.search(
            r"(?s)(\t\{ //StageId_PM_Stress\b.*?\t\t//Song info\s*\n\s*)"
            r"\{FIXED_DEC\([0-9]+,[0-9]+\),\s*FIXED_DEC\([0-9]+,[0-9]+\),\s*FIXED_DEC\([0-9]+,[0-9]+\)\}",
            _pico_stagedef,
        )
        if not _pico_stress:
            _pico_fail("Pico Stress stage definition", "unable to locate generated StageId_PM_Stress song-speed tuple")
        _pico_stagedef = (
            _pico_stagedef[:_pico_stress.start()] + _pico_stress.group(1) +
            _pico_expected_speed + _pico_stagedef[_pico_stress.end():]
        )
        _pico_stagedef_path.write_text(_pico_stagedef)

        def _pico_diff_check():
            return _pico_subprocess.run(
                ["git", "-C", str(_pico_root), "diff", "--check"],
                stdout=_pico_subprocess.PIPE, stderr=_pico_subprocess.STDOUT, text=True,
            )

        _pico_first = _pico_diff_check()
        if _pico_first.returncode:
            _pico_fix_lines = {}
            _pico_eof_files = set()
            for _pico_item in (_pico_first.stdout or "").splitlines():
                _pico_match = _pico_re.match(
                    r"^(.+?):(\d+): (trailing whitespace|space before tab in indent)\.$", _pico_item
                )
                if _pico_match:
                    _pico_fix_lines.setdefault(_pico_match.group(1), set()).add(int(_pico_match.group(2)))
                    continue
                _pico_match = _pico_re.match(r"^(.+?):(\d+): new blank line at EOF\.$", _pico_item)
                if _pico_match:
                    _pico_eof_files.add(_pico_match.group(1))

            for _pico_rel, _pico_numbers in _pico_fix_lines.items():
                _pico_path = _pico_root / _pico_rel
                _pico_lines = _pico_path.read_text().splitlines(keepends=True)
                for _pico_number in sorted(_pico_numbers):
                    if not (1 <= _pico_number <= len(_pico_lines)):
                        continue
                    _pico_line = _pico_lines[_pico_number - 1]
                    if _pico_line.endswith("\r\n"):
                        _pico_body, _pico_newline = _pico_line[:-2], "\r\n"
                    elif _pico_line.endswith("\n"):
                        _pico_body, _pico_newline = _pico_line[:-1], "\n"
                    else:
                        _pico_body, _pico_newline = _pico_line, ""
                    _pico_body = _pico_body.rstrip(" \t")
                    _pico_indent_match = _pico_re.match(r"^[ \t]*", _pico_body)
                    _pico_indent = _pico_indent_match.group(0)
                    while " \t" in _pico_indent:
                        _pico_indent = _pico_indent.replace(" \t", "\t")
                    _pico_lines[_pico_number - 1] = _pico_indent + _pico_body[len(_pico_indent_match.group(0)):] + _pico_newline
                _pico_path.write_text("".join(_pico_lines))
            for _pico_rel in _pico_eof_files:
                _pico_path = _pico_root / _pico_rel
                _pico_path.write_text(_pico_path.read_text().rstrip("\r\n") + "\n")

            _pico_second = _pico_diff_check()
            if _pico_second.returncode:
                _pico_fail("Pico post-apply diff check", (_pico_second.stdout or _pico_first.stdout or "git diff --check failed")[-5000:])
            print("::notice title=Pico apply phase::git diff --check auto-cleaned exact Pico whitespace lines", flush=True)
        else:
            print("::notice title=Pico apply phase::git diff --check clean immediately after apply", flush=True)

        _pico_frozen = _pico_subprocess.run(
            ["sha256sum", "-c", "/tmp/charselect-v7-1-frozen.sha256"],
            stdout=_pico_subprocess.PIPE, stderr=_pico_subprocess.STDOUT, text=True,
        )
        if _pico_frozen.returncode:
            _pico_fail("Pico validation: frozen Character Select", _pico_frozen.stdout or "sha256sum failed")
        print("::notice title=Pico frozen Character Select::v7.1 RLE SHA check passed", flush=True)

        _pico_validation = r'''
import json, re
from pathlib import Path
assets=json.loads(Path('build/pico_mix_assets_v1.json').read_text())
content=json.loads(Path('build/pico_mix_content_v1.json').read_text())
movies=json.loads(Path('build/pico_mix_movies_v1.json').read_text())
assert assets['policy']=='authentic-v0.8.4-pico-mix-and-freeplay-source-frames-only'
assert assets['freeplay']['idle_frames']==42
assert assets['freeplay']['stream_bytes']==193536
assert assets['character_select']['slot']==3
assert assets['character_select']['frames']==10
assert assets['bloody_tankman_health_icon']['frames']==2
expected={
    'picodark.arc':(30,8),'picoxmas.arc':(30,8),'picohold.arc':(28,7),
    'picopix.arc':(30,8),'nenedark.arc':(16,4),'nenexmas.arc':(16,4),
    'nenepix.arc':(10,3),'spookydk.arc':(15,4),'tankbldy.arc':(22,6),
    'otis.arc':(12,3),
}
for name,(frames,pages) in expected.items():
    assert assets['characters'][name]['frames']==frames, name
    assert assets['characters'][name]['pages']==pages, name
assert len(content['songs'])==15
assert len(content['charts'])==45
assert content['events']['total']==1172
assert len(content['durations_centiseconds'])==15
assert len(content['audio'])==4
assert all(row['bytes'] > 0 and row['bytes'] % 2336 == 0 for row in content['audio'])
assert movies['policy']=='official-v0.8.4-stress-pico-cutscene-only'
assert movies['frames'] > 0 and movies['bytes'] % 2336 == 0
assert movies['ending']['frames'] > 0 and movies['ending']['bytes'] % 2336 == 0
for index in range(1,16):
    for suffix in 'enh':
        path=Path(f'upstream/iso/chart/10.{index}{suffix}.cht')
        assert path.is_file() and path.stat().st_size > 0, path
for path in (
    'upstream/iso/music/picomix0.xa','upstream/iso/music/picomix1.xa',
    'upstream/iso/music/picomix2.xa','upstream/iso/music/picomix3.xa',
    'upstream/iso/menu/fppico.bin','upstream/iso/menu/fppico.tim',
    'upstream/iso/menu/fpbgp.tim','upstream/iso/menu/fpanimp.tim',
    'upstream/iso/menu/cspico.rle','upstream/iso/menu/cspc71a.tim',
    'upstream/iso/menu/cspc71b.tim','upstream/iso/movie/pstrs.str',
    'upstream/iso/movie/pstrend.str','upstream/iso/stage/pmblood.tim',
):
    file=Path(path); assert file.is_file() and file.stat().st_size > 0, path
menu=Path('upstream/src/menu.c').read_text()
stage=Path('upstream/src/stage.c').read_text()
joined='\n'.join(Path('upstream/src',name).read_text().lower() for name in (
    'stage.c','stage.h','audio.c','audio.h','menu.c','stage/picomix.c','stage/picomix.h'))
for marker in (
    'stageid_pm_bopeebo','stageid_pm_stress','xa_pm_bopeebo','xa_pm_stress',
    'picomix_applyhit','picomix_applymiss','picomix_playmissdirection',
    'picomix_applycameratarget','pico_stress_intro_frames','pico_stress_end_frames',
    'picomix_drawhealthicon','picomix_exit','menu_fp_pico_songs',
    'fppico.bin;1','cspico.rle;1','cspico_name_x',
):
    assert marker in joined, marker
assert stage.count('PicoMix_ApplyMiss(note);')==2
assert stage.count('PicoMix_ApplyCameraTarget();')==2
assert stage.count('PicoMix_ApplyCameraZoom();')==2
assert stage.count('PicoMix_DrawHealthIcon(-1)')==1
assert 'menu_freeplay_player = menu_cs_grid == 3 ? MenuPlayer_Pico' in menu
assert 'i==3 || i==4' in menu
assert 'menu_fp_songs[Menu_FreeplaySongIndex(option)].text' in menu
assert 'menu_freeplay_player == MenuPlayer_Boyfriend || menu_freeplay_player == MenuPlayer_Pico' in menu
runtime=Path('upstream/src/stage/picomix.c').read_text()
assert 's16 step = stage.song_step;' in runtime
assert 'pm_scroll_to = (event->flags & 1)' in runtime
assert 'pm_stress_session_active' in runtime
stagedef=Path('upstream/src/stagedef_disc1.h').read_text()
assert '{FIXED_DEC(15,10),FIXED_DEC(18,10),FIXED_DEC(23,10)}' in stagedef
assert '{FIXED_DEC(25,10),FIXED_DEC(29,10),FIXED_DEC(32,10)}' in stagedef
for source in Path('upstream/src/character').glob('pico*.c'):
    assert 'IO_Read("\\\\CHAR\\\\' in source.read_text(), source
xml=Path('upstream/funkin.xml').read_text()
assert '<dir name = "week10">' in xml and 'pmblood.tim' in xml
long_names=[name for name in re.findall(r'<file name = "([^"]+)"',xml) if len(name)>12]
assert not long_names, long_names
'''
        try:
            exec(compile(_pico_validation, "pico_workflow_validation", "exec"), {})
        except BaseException:
            _pico_fail("Pico mirrored workflow validation", _pico_traceback.format_exc()[-7000:])
        print("::notice title=Pico complete preflight::frozen SHA and full workflow validation passed", flush=True)
'''
    target.write_text(source + guard)
    phase("installed post-apply guard")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ending-atlas", type=Path, required=True)
    parser.add_argument("--ending-audio", type=Path, required=True)
    parser.add_argument("--ending-out", type=Path, required=True)
    parser.add_argument("--psxavenc", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, default=Path("ffmpeg"))
    parser.add_argument("--header", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.source.is_file():
        raise RuntimeError(f"official Stress Pico Mix cutscene missing: {args.source}")
    if not args.ending_audio.is_file():
        raise RuntimeError(f"official Stress Pico Mix ending audio missing: {args.ending_audio}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.ending_out.parent.mkdir(parents=True, exist_ok=True)

    phase("opening STR encode started")
    run_checked([
        str(args.psxavenc), "-q", "-t", "str", "-v", "v2",
        "-f", "37800", "-b", "4", "-c", "2", "-s", "320x240",
        "-r", "15", "-x", "2", str(args.source), str(args.out),
    ], "Pico opening STR encode")
    frames = encoded_frame_count(args.out)
    phase("opening STR encode completed")

    with tempfile.TemporaryDirectory() as directory:
        ending_source, ending_metadata = build_ending(args.ending_atlas, args.ending_audio, args.ffmpeg, Path(directory))
        phase("ending STR encode started")
        run_checked([
            str(args.psxavenc), "-q", "-t", "str", "-v", "v2",
            "-f", "37800", "-b", "4", "-c", "2", "-s", "320x240",
            "-r", str(FPS), "-x", "2", str(ending_source), str(args.ending_out),
        ], "Pico ending STR encode")
    ending_frames = encoded_frame_count(args.ending_out)
    phase("ending STR encode completed")

    args.header.parent.mkdir(parents=True, exist_ok=True)
    args.header.write_text(
        "#ifndef _PICO_MIX_MOVIES_GENERATED_H\n#define _PICO_MIX_MOVIES_GENERATED_H\n"
        f"#define PICO_STRESS_INTRO_FRAMES {frames}\n#define PICO_STRESS_END_FRAMES {ending_frames}\n#endif\n"
    )
    report = {
        "policy": "official-v0.8.4-stress-pico-cutscene-only",
        "source": args.source.name,
        "file": args.out.name,
        "frames": frames,
        "bytes": args.out.stat().st_size,
        "ending": {
            "source": args.ending_atlas.name,
            "audio": args.ending_audio.name,
            "file": args.ending_out.name,
            "frames": ending_frames,
            "bytes": args.ending_out.stat().st_size,
            "intermediate_video": ending_metadata,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    install_post_apply_guard()
    phase("report completed")


if __name__ == "__main__":
    phase("movie builder started")
    try:
        main()
    except BaseException as exc:
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        print(f"::error title=Pico Mix movie failure::{workflow_escape(detail[-6000:])}", flush=True)
        raise
    else:
        phase("movie builder completed")
