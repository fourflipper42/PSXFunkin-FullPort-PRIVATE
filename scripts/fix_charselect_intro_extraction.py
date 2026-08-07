#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('usage: fix_charselect_intro_extraction.py <builder.py>')

path = Path(sys.argv[1])
s = path.read_text()
start = s.find('def extract_intro_frames(')
if start < 0:
    raise SystemExit('extract_intro_frames function not found')
end = s.find('\ndef ', start + 5)
if end < 0:
    raise SystemExit('could not locate end of extract_intro_frames')

replacement = r'''def extract_intro_frames(video: Path, count: int) -> tuple[list[Image.Image], float]:
    if not video.is_file():
        raise FileNotFoundError(video)
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video)
    ], check=True, text=True, capture_output=True)
    duration = float(probe.stdout.strip())
    if duration <= 0:
        raise RuntimeError("introSelect video has invalid duration")
    result: list[Image.Image] = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for i in range(count):
            # Stay inside the final decodable timestamp. The v0.8.4 container's
            # reported duration extends slightly beyond its final video frame.
            nominal = duration * i / max(1, count - 1)
            end_guard = max(0.12, duration / max(1, count) * 0.75)
            t = min(nominal, max(0.0, duration - end_guard))
            out = td / f"intro-{i:02d}.png"
            extracted = False
            for backoff in (0.0, 0.05, 0.10, 0.20, 0.40, 0.80):
                seek = max(0.0, t - backoff)
                if out.exists():
                    out.unlink()
                proc = subprocess.run([
                    "ffmpeg", "-v", "error", "-y", "-ss", f"{seek:.6f}", "-i", str(video),
                    "-frames:v", "1", str(out)
                ], check=False)
                if proc.returncode == 0 and out.is_file() and out.stat().st_size > 0:
                    extracted = True
                    break
            if not extracted:
                raise RuntimeError(f"failed to decode introSelect frame {i} near {t:.3f}s")
            image = Image.open(out).convert("RGBA")
            result.append(base.crop_4_3(image).resize((SCENE_W, SCENE_H), Image.Resampling.LANCZOS))
    return result, duration

'''

s2 = s[:start] + replacement + s[end + 1:]
if s2.count('def extract_intro_frames(') != 1:
    raise SystemExit('intro extraction patch did not produce exactly one function')
path.write_text(s2)
print('patched robust introSelect frame extraction')
