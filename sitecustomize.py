"""CI-only diagnostics for the final Pico Mix inline validation block."""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _escape(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


# stdin-based Python validation runs from the repository root, so this module is
# imported automatically there. Stay completely inert during every earlier
# builder/py_compile invocation and outside GitHub Actions.
if (
    os.environ.get("GITHUB_ACTIONS") == "true"
    and Path("build/pico_mix_assets_v1.json").is_file()
    and Path("build/pico_mix_content_v1.json").is_file()
    and Path("build/pico_mix_movies_v1.json").is_file()
    and Path("upstream/src/stage/picomix.c").is_file()
):
    _original_hook = sys.excepthook

    def _pico_validation_hook(exc_type, exc, tb):
        detail = "".join(traceback.format_exception(exc_type, exc, tb))[-10000:]
        print(
            "::error title=Pico inline validation failure::" + _escape(detail),
            file=sys.stderr,
            flush=True,
        )
        _original_hook(exc_type, exc, tb)

    sys.excepthook = _pico_validation_hook
