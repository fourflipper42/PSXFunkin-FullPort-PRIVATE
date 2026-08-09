#!/usr/bin/env python3
"""Temporary CI launcher for the unchanged Pico Mix asset builder."""
from __future__ import annotations

from pathlib import Path
import runpy
import traceback


def main() -> None:
    implementation = Path(__file__).with_name("build_pico_mix_assets_impl.py")
    try:
        runpy.run_path(str(implementation), run_name="__main__")
    except BaseException as exc:
        trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        annotation = (
            trace.replace("%", "%25")
            .replace("\r", "%0D")
            .replace("\n", "%0A")
        )
        print(f"::error title=Pico asset builder traceback::{annotation}", flush=True)
        print("PICO_ASSET_TRACEBACK_BEGIN", flush=True)
        print(trace, end="" if trace.endswith("\n") else "\n", flush=True)
        print("PICO_ASSET_TRACEBACK_END", flush=True)
        raise


if __name__ == "__main__":
    main()
