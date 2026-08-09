#!/usr/bin/env python3
"""Temporary CI launcher for the unchanged Pico movie builder."""
from pathlib import Path
import runpy
import traceback

try:
    runpy.run_path(str(Path(__file__).with_name("build_pico_mix_movies_impl.py")), run_name="__main__")
except BaseException as exc:
    trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    annotation = trace.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::error title=Pico movie builder traceback::{annotation}", flush=True)
    print("PICO_MOVIE_TRACEBACK_BEGIN\n" + trace + "PICO_MOVIE_TRACEBACK_END", flush=True)
    raise
