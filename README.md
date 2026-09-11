# PSXFunkin Full Port

Work in progress targeting real PlayStation hardware and one CD.
This repository contains patches and asset converters for cuckydev/PSXFunkin
revision `850e0207479d8fb658bdc7637f6bfbc28a2b4066`; it is not a self-contained game.

See [the 0.8.4 rebuild checkpoint](docs/V084_PARITY.md) for the expanded scope,
measured animation-bank prototype, and explicit unfinished features.

## September 10, 2026 repair pass

- Fixed patch ordering, incorrect hunk counts, and the movie patch's missing
  final-newline mismatch. Removed redundant Base64 copies of the runtime patch.
- Added a revision/clean-tree checked patch applicator.
- Split chart sections at tempo and camera-focus changes, rather than rounding
  changes to whole measures. Derive omitted beat positions, reject invalid
  tempo/lane/position data, and avoid phantom sustain tails for tiny holds.
- Preserve opaque black in TIM textures and stop premultiplying edge colors
  against black during palette conversion.
- Terminate ARC directories even when all 16 texture slots are occupied.
- Avoid resetting generated player death/custom animations to idle on beats.
  Missing required animations now fail conversion instead of using frame zero.
- Generate Weekend 1 playback lengths from encoded XA sector counts.
- Validate BIN sector alignment, CUE references, and a conservative 333,000-sector
  (74-minute) disc budget. Store the result in the release's `disc.json`.
- Run converter regression tests in CI before downloading the base source/assets.

## Local checks

Python 3.10+ and Pillow are required for converter tests:

```sh
python3 -m unittest discover -s tests -v
```

To prepare the source, run from this repository directory:

```sh
git clone https://github.com/cuckydev/PSXFunkin.git upstream
git -C upstream checkout 850e0207479d8fb658bdc7637f6bfbc28a2b4066
python3 scripts/apply_patches.py upstream
```

The applicator expects a fresh clean checkout. If a patch fails, it leaves
already applied patches in place for diagnosis; use a fresh checkout to retry.
The canonical patches are applied in filename order, then `overlay/` sources
are copied into the prepared tree by the same applicator.

## Full build inputs

The GitHub Actions workflow downloads these files from this repository's
`assets-v084` release:

- `Shared.Shaders.Scripts.Music.Images.and.Data.zip`
- `Sounds.and.Songs.zip`
- `WEEKS.zip`

Extract all three into `official-v084/` as shown in the workflow. They are available from the release and were used for the baseline CI build.
CI additionally downloads the VCR font and credits JSON at the pinned official
assets revision.
The workflow also obtains the MIPS compiler, PsyQ compatibility libraries,
psxavenc, and mkpsxiso. See `.github/workflows/ps1-build.yml` for exact commands.
The audio, movie and menu generators write headers required by the patched C
source; run them before compiling. No SDK or official asset files are bundled.

## Verification and remaining work

28 host tests pass, including the menu state machine under address/undefined
behavior sanitizers. Eight patches and the overlay apply to the pinned base.
The menu revision completed CI, including the MIPS link and a
399,228,480-byte BIN (169,740 sectors). See the checkpoint document for exact
commit coverage and unfinished features. No emulator or real-console verification
is claimed.

Known remaining work:

- Erect/Nightmare currently load different charts but still select each stage's
  base music track/channel and Hard scroll speed. Dedicated remix audio routing,
  lengths, and speeds must be implemented and checked against the actual assets.
- Weeks 1–7 use upstream audio while their charts are regenerated from v0.8.4;
  check offsets, duration, and vocal behavior against the supplied release.
- Validate every character's source labels, death/retry flow, texture placement,
  stage composition, and animation pacing with real assets. The generator samples
  a limited set of frames and does not reproduce all modern visual effects.
- Measure executable/heap/stack use, including movie playback buffers, and test
  story transitions, retries, cutscene skip/return, input timing, and CD reads.
- Build the final image, measure its actual sector count, and test it on the
  target console. The size validator is a packaging check, not a boot guarantee.

Reference for the opaque-black texture fix:
https://psx-spx.consoledev.net/graphicsprocessingunitgpu/#texture-color-black-limitations
