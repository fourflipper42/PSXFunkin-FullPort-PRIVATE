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

import os
from pathlib import Path
import re
import runpy
import site
import sys
import traceback


CORE = Path(__file__).with_name("build_pico_mix_content_core.py")
core = runpy.run_path(str(CORE), run_name="pico_mix_content_core")


def install_ci_inline_traceback_hook() -> None:
    """Make the later stdin validator expose its exact failed assertion in CI.

    Repository-root sitecustomize.py is not imported by the Actions Python
    startup used for the heredoc validator. Python does import usercustomize
    from its user site, however, so install the same narrowly-scoped hook there
    before the later Pico asset/movie/apply/validation processes start.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    user_site = Path(site.getusersitepackages())
    user_site.mkdir(parents=True, exist_ok=True)
    hook = r'''from __future__ import annotations
import os
import sys
import traceback
from pathlib import Path


def _pico_escape(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


if (
    os.environ.get("GITHUB_ACTIONS") == "true"
    and Path("build/pico_mix_assets_v1.json").is_file()
    and Path("build/pico_mix_content_v1.json").is_file()
    and Path("build/pico_mix_movies_v1.json").is_file()
    and Path("upstream/src/stage/picomix.c").is_file()
):
    _pico_original_hook = sys.excepthook

    def _pico_inline_hook(exc_type, exc, tb):
        detail = "".join(traceback.format_exception(exc_type, exc, tb))[-12000:]
        print(
            "::error title=Pico inline validation failure::" + _pico_escape(detail),
            file=sys.stderr,
            flush=True,
        )
        _pico_original_hook(exc_type, exc, tb)

    sys.excepthook = _pico_inline_hook
'''
    target = user_site / "usercustomize.py"
    target.write_text(hook)
    print(
        f"::notice title=Pico Mix diagnostics::installed inline validator traceback hook at {target}",
        flush=True,
    )


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


def _replace_c_function(text: str, signature: str, replacement: str, label: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise RuntimeError(f"{label}: signature missing")
    brace = text.find("{", start)
    if brace < 0:
        raise RuntimeError(f"{label}: opening brace missing")
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[:start] + replacement.rstrip() + text[index + 1:]
    raise RuntimeError(f"{label}: closing brace missing")


def patch_m1_mdec_v9() -> None:
    """Expose MDEC callback/completion failures instead of displaying fake frames."""
    try:
        iso_index = sys.argv.index("--iso-root")
        iso_root = Path(sys.argv[iso_index + 1])
    except (ValueError, IndexError):
        raise RuntimeError("M1 v9 requires --iso-root so strplay.c can be patched")

    strplay = iso_root.parent / "src/strplay.c"
    text = strplay.read_text()
    marker = "M1_MDEC_SYNC_V9"
    if marker in text:
        return

    # v8 proved the Sony 24-bit display path does not solve the corruption.
    # Return to the smaller inherited 16-bit path for the completion diagnostic.
    v8_line = "#define IS_RGB24\t1\t// M1_RGB24_V8: Sony PsyQ 24-bit movie output path"
    baseline_line = "#define IS_RGB24\t0\t// 0:16-bit playback, 1:24-bit playback (recommended for quality)"
    if v8_line in text:
        text = text.replace(v8_line, baseline_line, 1)
    if "#define IS_RGB24\t0" not in text:
        raise RuntimeError("M1 v9 expected the 16-bit STR output path")

    # FrameDone is written by the MDEC interrupt callback and polled by the main
    # thread. It must not be cached across the wait loop by the compiler.
    text, count = re.subn(
        r"(?m)^(\s*)int(\s+)FrameDone;",
        r"\1volatile int\2FrameDone;",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"M1 v9 FrameDone anchor changed: {count}")

    globals_anchor = "static int strPlayDone=0;"
    globals_patch = globals_anchor + r'''

/* M1_MDEC_SYNC_V9: callback/completion instrumentation. */
static volatile u_long strMdecCallbackCount = 0;
static volatile u_long strMdecFrameCallbackStart = 0;
static volatile int strMdecFailureCode = 0;'''
    if text.count(globals_anchor) != 1:
        raise RuntimeError(f"M1 v9 globals anchor changed: {text.count(globals_anchor)}")
    text = text.replace(globals_anchor, globals_patch, 1)

    callback_anchor = "static void strCallback() {\n"
    callback_patch = (
        "static void strCallback() {\n"
        "\t/* M1 v9: prove whether MDEC ever produces an output slice. */\n"
        "\tstrMdecCallbackCount++;\n"
    )
    if text.count(callback_anchor) != 1:
        raise RuntimeError(f"M1 v9 callback anchor changed: {text.count(callback_anchor)}")
    text = text.replace(callback_anchor, callback_patch, 1)

    reset_anchor = "\tstrEnv.FrameDone = 0;\n\n\tDecDCTReset(0);"
    reset_patch = (
        "\tstrEnv.FrameDone = 0;\n"
        "\tstrMdecCallbackCount = 0;\n"
        "\tstrMdecFrameCallbackStart = 0;\n"
        "\tstrMdecFailureCode = 0;\n\n"
        "\tDecDCTReset(0);"
    )
    if text.count(reset_anchor) != 1:
        raise RuntimeError(f"M1 v9 reset anchor changed: {text.count(reset_anchor)}")
    text = text.replace(reset_anchor, reset_patch, 1)

    frame_anchor = "\twhile (1) {\n\t\tDecDCTin(strEnv.VlcBuff_ptr[strEnv.VlcID], DCT_MODE);"
    frame_patch = (
        "\twhile (1) {\n"
        "\t\tstrMdecFrameCallbackStart = strMdecCallbackCount;\n"
        "\t\tDecDCTin(strEnv.VlcBuff_ptr[strEnv.VlcID], DCT_MODE);"
    )
    if text.count(frame_anchor) != 1:
        raise RuntimeError(f"M1 v9 frame-start anchor changed: {text.count(frame_anchor)}")
    text = text.replace(frame_anchor, frame_patch, 1)

    sync_impl = r'''static void strSync(STRENV *strEnv, int mode) {
    u_long cnt = WAIT_TIME;

    /* M1_MDEC_SYNC_V9: never turn an MDEC timeout into a fake completed frame. */
    while (strEnv->FrameDone == 0) {
        if (--cnt == 0) {
            if (strMdecCallbackCount == strMdecFrameCallbackStart)
                strMdecFailureCode = 5; /* no MDEC output callback */
            else
                strMdecFailureCode = 6; /* slices arrived, frame never completed */
            return;
        }
    }

    strEnv->FrameDone = 0;
}
'''
    text = _replace_c_function(
        text,
        "static void strSync(STRENV *strEnv, int mode) {",
        sync_impl,
        "M1 v9 strSync",
    )

    post_sync_anchor = "\t\tstrSync(&strEnv, 0);\n\t\tid = strEnv.RectID ? 0 : 1;"
    post_sync_patch = (
        "\t\tstrSync(&strEnv, 0);\n"
        "\t\tif (strMdecFailureCode != 0)\n"
        "\t\t\tbreak;\n"
        "\t\tid = strEnv.RectID ? 0 : 1;"
    )
    if text.count(post_sync_anchor) != 1:
        raise RuntimeError(f"M1 v9 post-sync anchor changed: {text.count(post_sync_anchor)}")
    text = text.replace(post_sync_anchor, post_sync_patch, 1)

    cleanup_anchor = (
        "\tDecDCToutCallback(0);\n"
        "\tStUnSetRing();\n"
        "\tCdControlB(CdlPause, 0, 0);\n"
        "\tMem_Free(workspace);\n"
        "}\n\nstatic void strCallback() {"
    )
    cleanup_patch = (
        "\tDecDCToutCallback(0);\n"
        "\tStUnSetRing();\n"
        "\tCdControlB(CdlPause, 0, 0);\n"
        "\tMem_Free(workspace);\n"
        "\tif (strMdecFailureCode != 0) {\n"
        "\t\tSetDispMask(1);\n"
        "\t\tif (strMdecFailureCode == 5)\n"
        "\t\t\tsprintf(error_msg, \"[M1V9 E5] no MDEC output callback\");\n"
        "\t\telse\n"
        "\t\t\tsprintf(error_msg, \"[M1V9 E6] MDEC frame incomplete\");\n"
        "\t\tErrorLock();\n"
        "\t\treturn;\n"
        "\t}\n"
        "}\n\nstatic void strCallback() {"
    )
    if text.count(cleanup_anchor) != 1:
        raise RuntimeError(f"M1 v9 final cleanup anchor changed: {text.count(cleanup_anchor)}")
    text = text.replace(cleanup_anchor, cleanup_patch, 1)

    strplay.write_text(text)
    verify = strplay.read_text()
    required = (
        marker,
        "volatile int\t\tFrameDone;",
        "strMdecCallbackCount++;",
        "strMdecFailureCode = 5",
        "strMdecFailureCode = 6",
        "[M1V9 E5] no MDEC output callback",
        "[M1V9 E6] MDEC frame incomplete",
    )
    missing = [item for item in required if item not in verify]
    if missing:
        raise RuntimeError(f"M1 v9 patch did not persist: {missing}")
    if "M1_RGB24_V8" in verify or "#define IS_RGB24\t1" in verify:
        raise RuntimeError("M1 v8 RGB24 diagnostic survived into v9")
    print(
        "::notice title=M1 STR diagnostic::v9 MDEC callback/completion instrumentation enabled",
        flush=True,
    )


def workflow_escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


if __name__ == "__main__":
    install_ci_inline_traceback_hook()
    print("::notice title=Pico Mix phase::content builder started", flush=True)
    try:
        core["main"]()
        patch_m1_mdec_v9()
    except BaseException as exc:
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        print(f"::error title=Pico Mix content failure::{workflow_escape(detail)}", flush=True)
        raise
    else:
        print("::notice title=Pico Mix phase::content builder completed", flush=True)
