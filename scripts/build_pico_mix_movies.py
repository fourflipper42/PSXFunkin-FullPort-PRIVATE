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
    print(f"::notice title=Pico Mix movie phase::{workflow_escape(message)}", flush=True)


def run_checked(command: list[str], label: str) -> str:
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output = (result.stdout or "").strip()
    if result.returncode != 0:
        short = output[-3000:] if output else "no diagnostic output"
        print(
            f"::error title={workflow_escape(label)}::{workflow_escape(short)}",
            flush=True,
        )
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
    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    if len(streams) != 1:
        raise RuntimeError(f"generated Pico ending has {len(streams)} video streams")
    stream = streams[0]
    color_space = stream.get("color_space")
    if color_space not in {"bt470bg", "smpte170m"}:
        raise RuntimeError(f"generated Pico ending has unsafe colorspace for psxavenc: {stream}")
    phase(
        "ending video metadata verified: "
        f"codec={stream.get('codec_name')} pix_fmt={stream.get('pix_fmt')} "
        f"colorspace={color_space} range={stream.get('color_range')}"
    )
    return stream


def build_ending(atlas_path: Path, audio: Path, ffmpeg: Path, temporary: Path) -> tuple[Path, dict[str, str]]:
    phase("ending atlas render started")
    atlas = AnimateAtlas(atlas_path)
    atlas_frames = atlas.timeline_length(atlas.root["TL"])
    frame_count = math.ceil((320 / 24) * FPS)

    # WonderfulToolchain/psxavenc passes AVCodecContext.colorspace directly to
    # sws_getCoefficients(). An unspecified generated-video colorspace therefore
    # reaches a libswscale path that the official Stress opening does not. Keep
    # the successful LE SSERAFIM H.264 handoff but explicitly tag BT.601 using
    # bt470bg (enum value 5, matching libswscale's ITU-601 coefficient table).
    # Disable B-frames as well so the temporary stream has no delayed frames.
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
            frame = Image.blend(
                frame.convert("RGB"), Image.new("RGB", frame.size, "black"), alpha
            ).convert("RGBA")
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
    metadata = probe_video(target, ffmpeg)
    return target, metadata


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

    ending_metadata: dict[str, str]
    with tempfile.TemporaryDirectory() as directory:
        ending_source, ending_metadata = build_ending(
            args.ending_atlas, args.ending_audio, args.ffmpeg, Path(directory)
        )
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
        "#ifndef _PICO_MIX_MOVIES_GENERATED_H\n"
        "#define _PICO_MIX_MOVIES_GENERATED_H\n"
        f"#define PICO_STRESS_INTRO_FRAMES {frames}\n"
        f"#define PICO_STRESS_END_FRAMES {ending_frames}\n"
        "#endif\n"
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
    phase("report completed")


if __name__ == "__main__":
    phase("movie builder started")
    try:
        main()
    except BaseException as exc:
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        print(
            f"::error title=Pico Mix movie failure::{workflow_escape(detail[-6000:])}",
            flush=True,
        )
        raise
    else:
        phase("movie builder completed")
