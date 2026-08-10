#!/usr/bin/env python3
"""Build Pico Mix content while resolving v0.8.4 visual-variant vocal IDs.

Funkin v0.8.4 metadata can identify a visual character variant (for example
``spooky-dark`` or ``pico-dark``) while the shipped Pico Mix vocal stem keeps
the base singer name (``Voices-spooky-pico.ogg`` / ``Voices-pico-pico.ogg``).
This launcher preserves the content builder and resolves only to an existing
official file in that song directory. No substitute or generated audio is
allowed.
"""
from __future__ import annotations

from pathlib import Path
import runpy
import traceback


CORE = Path(__file__).with_name("build_pico_mix_content_core.py")
core = runpy.run_path(str(CORE), run_name="pico_mix_content_core")


def resolve_official_voice(song_dir: Path, requested: str) -> str:
    direct = song_dir / requested
    if direct.is_file():
        return requested

    prefix = "Voices-"
    suffix = "-pico.ogg"
    if not requested.startswith(prefix) or not requested.endswith(suffix):
        return requested

    character = requested[len(prefix):-len(suffix)]
    parts = character.split("-")
    # Keep the most-specific official stem possible. This mirrors the shipped
    # v0.8.4 naming relationship: a visual suffix such as -dark, -christmas,
    # -pixel, -bloody, or -holding-nene may not be part of the vocal filename.
    for end in range(len(parts) - 1, 0, -1):
        candidate = f"Voices-{'-'.join(parts[:end])}-pico.ogg"
        if (song_dir / candidate).is_file():
            print(f"Resolved official Pico vocal {requested} -> {candidate}")
            return candidate
    return requested


def mix_song(ffmpeg: Path, song_dir: Path, voices: list[str], target: Path) -> None:
    resolved: list[str] = []
    for requested in voices:
        voice = resolve_official_voice(song_dir, requested)
        if voice not in resolved:
            resolved.append(voice)

    inputs = [song_dir / "Inst-pico.ogg"] + [song_dir / voice for voice in resolved]
    for source in inputs:
        if not source.is_file():
            raise RuntimeError(f"official Pico Mix audio missing: {source}")

    command = [ffmpeg, "-y", "-loglevel", "error"]
    for source in inputs:
        command += ["-i", source]
    labels = "".join(f"[{index}:a]" for index in range(len(inputs)))
    command += [
        "-filter_complex", f"{labels}amix=inputs={len(inputs)}:duration=longest:normalize=0[m]",
        "-map", "[m]", "-ar", "18900", "-ac", "2", target,
    ]
    core["run"](command)


core["mix_song"] = mix_song
# runpy.run_path() returns a copy of the executed globals mapping. The function
# object keeps the original mapping in __globals__, so bind the resolver there
# as well or main() will continue calling the unwrapped core mix_song().
core["main"].__globals__["mix_song"] = mix_song


def workflow_escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


if __name__ == "__main__":
    print("::notice title=Pico Mix phase::content builder started", flush=True)
    try:
        core["main"]()
    except BaseException as exc:
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        print(f"::error title=Pico Mix content failure::{workflow_escape(detail)}", flush=True)
        raise
    else:
        print("::notice title=Pico Mix phase::content builder completed", flush=True)

# CI trigger: root sitecustomize.py exposes the final stdin validation traceback.
