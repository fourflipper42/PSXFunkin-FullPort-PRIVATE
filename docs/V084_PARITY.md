# 0.8.4 parity rebuild — development checkpoint

Target: real PS1, one CD, menus reflowed for 4:3, all official playable content,
complete audio/cutscenes, and smooth source animation. This checkpoint is not a
finished port, and no console test has been performed.

## Exact reference

- Funkin source tag v0.8.4: `90eabf0b38fd2fd79fbe88f1f37a0efe92052679`.
- Its assets submodule: `d1d027d4747aaba151c6df121ea736c31d6aed38`.
- Original PSXFunkin base: `850e0207479d8fb658bdc7637f6bfbc28a2b4066`.
- The repository's `assets-v084` ZIP release was downloaded and extracted.
  It omits some reference files, including Spaghetti audio. Missing runtime
  reference files were recovered from the exact assets commit for local inspection.
  The CI input download still uses the three original ZIPs; it does not yet fetch
  these additions or include the collab content in the game.

## Confirmed coverage and gaps

| Area | Current implementation | Required work |
| --- | --- | --- |
| Menus | Original PSXFunkin menus; a Week 8 label fix | Rebuild title, main, story, new freeplay, character select, options, pause, results and credits using 0.8.4 artwork/layout behavior reflowed for 4:3 |
| Charts | 98 Tutorial/Weeks 1–7 and 14 Weekend 1 charts convert successfully | Add all playable character variants and Spaghetti; route scroll speeds, metadata, events and characters per variant |
| Audio | Original upstream tracks plus a Weekend 1 encoder | Regenerate/remap base, Erect/Nightmare and character variants; retain separate vocal behavior; verify offsets and endings |
| Cutscenes | Weekend 1 only, 15 fps conversion | Cover all gameplay cutscenes and censorship variants; preserve source timing/aspect without stretching 16:9 footage |
| Characters | Existing converter samples 2–4 frames per animation | Integrate the full-frame bank prototype, preserve source frame selection/timing, offsets, flips and event animations |
| Stage effects | Legacy stages and static Weekend 1 backgrounds | Reimplement scripted effects and variant backgrounds within GPU/CPU limits |
| Memory | Fixed 1 MiB game heap | Redesign asset lifetimes and death/menu loading; measure peak heap, stack and decoder buffers |
| Disc | Size and BIN/CUE checks added | Measure the complete disc after new media/art; size checks do not prove bootability |
| Hardware | No console test | Test timing, loading, input, cutscene skip/return and memory use on target hardware |

## Full-frame storage prototype

`build_full_atlas.py` renders every labeled source timeline frame at an explicit
scale (default 0.22). It refuses textures larger than 256x256 at that scale rather
than shrinking them silently. It uses one 256-color palette per bank, retains
repeated frames in the timeline, deduplicates identical pixel buffers, and RLE
compresses the indexed data losslessly. The current game does **not** load this
format yet. `overlay/src/framecodec.c` is a standalone, host-tested decoder,
not a completed texture loader/animation runtime. Do not confuse generated banks
with an integrated or performance-tested PS1 feature.

Measurements from the exact reference atlases:

| Atlas | Distinct timeline positions | Unique indexed images | Bank bytes |
| --- | ---: | ---: | ---: |
| Pico basic | 73 | 15 | 72,430 |
| Pico playable | 479 | 112 | 579,390 |
| Pico death | 144 | 96 | 599,491 |
| Nene | 156 | 81 | 296,224 |
| Darnell | 152 | 85 | 378,051 |
| Pico Blazin | 383 | 102 | 415,221 |
| Darnell Blazin | 89 | 45 | 190,471 |

Some source labels overlap. Distinct timeline position counts therefore differ
from the sum of every label's duration; the animation index lists retain all
labeled positions. All source frame rates in this set are 24 fps. These byte
counts exclude the game executable, other assets, runtime buffers and allocator
headers. Loading all Pico banks plus Nene and Darnell exceeds the existing heap;
death assets must have a different lifetime, and further memory work is needed.

Example prototype build (the existing release ZIPs must already be extracted):

```sh
python3 scripts/ps1asset/build_full_atlas.py \
  official-v084/shared/images/characters/pico/basic-animations \
  build/pico-basic.fbk
```

Validation: 23 host tests pass, including native C decoding, malformed-stream
rejection, frame deduplication without timing loss, palette transparency, chart
conversion and disc packaging checks. All seven restored source patches apply.
Full official chart/Weekend 1 asset conversion passes. A portable MIPS compiler
and PsyQ libraries were recovered locally, but the prebuilt psxavenc v0.3.1
aborted even on a one-second silent WAV in this execution environment. No local
full media build, linked game, disc image, emulator run or hardware validation
is claimed. CI builds psxavenc from source and must be checked separately.
