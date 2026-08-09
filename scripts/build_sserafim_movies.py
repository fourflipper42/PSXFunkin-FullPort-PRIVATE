#!/usr/bin/env python3
"""Pre-render the official SPAGHETTI intro and ending as PS1 STR movies."""
from __future__ import annotations

import argparse
import json
import math
import struct
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "ps1asset"))
from animateatlas_flatten import AnimateAtlas, render_leaves, render_leaves_fixed

SECTOR = 2336
STR_MAGIC = b"\x60\x01\x01\x80"
FPS = 15


def run(command) -> None:
    subprocess.run([str(value) for value in command], check=True)


def video_writer(ffmpeg: Path, target: Path, seconds: float):
    frames = math.ceil(seconds * FPS)
    process = subprocess.Popen([
        str(ffmpeg), "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "320x240", "-r", str(FPS), "-i", "-",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p", str(target),
    ], stdin=subprocess.PIPE)
    return process, frames


def fit_sprite(atlas: AnimateAtlas, frame: int, max_size: tuple[int, int]) -> Image.Image:
    image, _ = render_leaves(atlas.leaves_for_frame(frame))
    scale = min(max_size[0] / image.width, max_size[1] / image.height)
    return image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)


def build_intro(root: Path, stage_preview: Path, ffmpeg: Path, target: Path) -> int:
    cutscene = AnimateAtlas(root / "sserafim/images/cutscene/cutsceneMain")
    gf = AnimateAtlas(root / "sserafim/images/cutscene/gfGetUp")
    bf = AnimateAtlas(root / "sserafim/images/cutscene/bfGetUp")
    preview = Image.open(stage_preview).convert("RGB").resize((320, 240), Image.Resampling.LANCZOS)
    process, frame_count = video_writer(ffmpeg, target, 730 / 24)
    assert process.stdin is not None
    for output_frame in range(frame_count):
        time = output_frame / FPS
        source_frame = min(630, math.floor(time * 24))
        if time < 563 / 24:
            camera_t = min(1.0, time / 3.0)
            # circOut matches the official camera tween closely.
            eased = math.sqrt(max(0.0, 1.0 - (camera_t - 1.0) ** 2))
            camera_y = -200.0 + 500.0 * eased
            zoom = 0.5 + 0.2 * eased
            scale = zoom * 0.25
            transform = (scale, 0.0, 0.0, scale,
                         160.0 + (-395.0 - 660.0) * scale,
                         120.0 + (10.0 - camera_y) * scale)
            image = render_leaves_fixed(cutscene.leaves_for_frame(source_frame), (320, 240), transform).convert("RGB")
        elif time < 650 / 24:
            crash = time - 563 / 24
            if crash < 1.25:
                shade = round(255 * max(0.0, 1.0 - crash / 1.25))
                image = Image.new("RGB", (320, 240), (shade, shade, shade))
            else:
                image = Image.new("RGB", (320, 240), "black")
        else:
            fade = min(1.0, max(0.0, (time - 650 / 24) / 3.0))
            image = Image.blend(Image.new("RGB", (320, 240), "black"), preview, fade)
            if time >= 710 / 24:
                local = min(19, max(0, math.floor((time - 710 / 24) * 24)))
                gf_image = fit_sprite(gf, min(123, 1 + local), (105, 125))
                bf_image = fit_sprite(bf, min(128, 1 + local), (110, 130))
                layer = image.convert("RGBA")
                layer.alpha_composite(gf_image, (112, 62))
                layer.alpha_composite(bf_image, (215, 88))
                image = layer.convert("RGB")
        process.stdin.write(image.tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg failed while rendering SPAGHETTI intro")
    return frame_count


def build_ending(root: Path, ffmpeg: Path, target: Path) -> int:
    end1 = Image.open(root / "sserafim/images/end/end1.png").convert("RGBA")
    end2 = Image.open(root / "sserafim/images/end/end2.png").convert("RGBA")
    for image in (end1, end2):
        image.thumbnail((300, 220), Image.Resampling.LANCZOS)
    process, frame_count = video_writer(ffmpeg, target, 9.0)
    assert process.stdin is not None
    for output_frame in range(frame_count):
        time = output_frame / FPS
        frame = Image.new("RGBA", (320, 240), "black")
        if time < 4.0:
            frame.alpha_composite(end1, ((320 - end1.width) // 2, (240 - end1.height) // 2))
        elif time < 8.0:
            frame.alpha_composite(end2, (max(0, 310 - end2.width), max(0, 230 - end2.height)))
        process.stdin.write(frame.convert("RGB").tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg failed while rendering SPAGHETTI ending")
    return frame_count


def encoded_frame_count(path: Path) -> int:
    data = path.read_bytes()
    if len(data) % SECTOR:
        raise RuntimeError(f"{path} is not {SECTOR}-byte sector aligned")
    maximum = 0
    for offset in range(0, len(data), SECTOR):
        sector = data[offset:offset + SECTOR]
        if sector[2] == 0x48 and sector[8:12] == STR_MAGIC:
            maximum = max(maximum, struct.unpack_from("<I", sector, 16)[0])
    if maximum <= 0:
        raise RuntimeError(f"no STR video frames found in {path}")
    return maximum


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--stage-preview", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--psxavenc", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, default=Path("ffmpeg"))
    parser.add_argument("--header", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        intro_video = temp / "intro-silent.mp4"
        ending_video = temp / "ending-silent.mp4"
        intro_source_frames = build_intro(args.root, args.stage_preview, args.ffmpeg, intro_video)
        ending_source_frames = build_ending(args.root, args.ffmpeg, ending_video)

        intro_media = temp / "intro.mp4"
        run([
            args.ffmpeg, "-y", "-loglevel", "error", "-i", intro_video,
            "-i", args.root / "sserafim/sounds/cutscene/startCutscene.ogg",
            "-filter_complex", "[1:a]adelay=833|833[a]", "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-t", f"{intro_source_frames / FPS:.6f}", intro_media,
        ])
        ending_media = temp / "ending.mp4"
        run([
            args.ffmpeg, "-y", "-loglevel", "error", "-i", ending_video,
            "-i", args.root / "sserafim/sounds/cutscene/end1.ogg",
            "-i", args.root / "sserafim/sounds/cutscene/end2.ogg",
            "-filter_complex", "[2:a]adelay=4000|4000[e2];[1:a][e2]amix=inputs=2:duration=longest:normalize=0[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-t", f"{ending_source_frames / FPS:.6f}", ending_media,
        ])

        outputs = []
        for source, name, source_frames in (
            (intro_media, "sfintro.str", intro_source_frames),
            (ending_media, "sfend.str", ending_source_frames),
        ):
            target = args.out / name
            run([args.psxavenc, "-q", "-t", "str", "-v", "v2", "-f", "37800", "-b", "4", "-c", "2", "-s", "320x240", "-r", str(FPS), "-x", "2", source, target])
            outputs.append({
                "file": name, "source_frames": source_frames,
                "frames": encoded_frame_count(target), "bytes": target.stat().st_size,
            })

    args.header.parent.mkdir(parents=True, exist_ok=True)
    args.header.write_text(
        "#ifndef _SSERAFIM_MOVIES_GENERATED_H\n#define _SSERAFIM_MOVIES_GENERATED_H\n"
        f"#define SSERAFIM_INTRO_FRAMES {outputs[0]['frames']}\n"
        f"#define SSERAFIM_END_FRAMES {outputs[1]['frames']}\n#endif\n"
    )
    report = {
        "policy": "official-v0.8.4-sserafim-art-and-cutscene-audio-only",
        "movies": outputs,
        "intro_timeline_frames": 730,
        "intro_timeline_fps": 24,
        "ps1_fps": FPS,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
