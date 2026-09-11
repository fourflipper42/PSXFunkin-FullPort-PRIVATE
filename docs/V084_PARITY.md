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
  CI also fetches the pinned VCR font and credits JSON. It does not yet fetch
  Spaghetti audio or include the collab content in the game.

## Confirmed coverage and gaps

| Area | Current implementation | Required work |
| --- | --- | --- |
| Menus | Official animated title logo/GF and five main labels; 4:3 story/song/options lists; official intro messages and scrolling credits | Modern story character art, freeplay capsules/DJ/character select, full options, pause/results, title confirmation animation and menu sound effects remain unfinished |
| Charts | 98 Tutorial/Weeks 1–7 and 14 Weekend 1 charts convert successfully | Add all playable character variants and Spaghetti; route scroll speeds, metadata, events and characters per variant |
| Audio | Original upstream tracks plus a Weekend 1 encoder | Regenerate/remap base, Erect/Nightmare and character variants; retain separate vocal behavior; verify offsets and endings |
| Cutscenes | Three Weekend 1 movies at source 24 fps, centered letterboxing, complete encoded/decoded frame checks | Cover Week 7 and remaining gameplay/censorship variants; verify synchronized playback on hardware |
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
compresses the indexed data losslessly. The menu runtime now loads this format through `overlay/src/framebank.c`.
The bounded decoder uploads 8-bit textures through a shared 66,080-byte buffer;
identical frame payloads reuse the current GPU upload while keeping their
timeline entries. Character banks remain prototypes and are not enabled in
gameplay. Runtime performance has not been measured on a console.

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

## Menu runtime checkpoint

All 105 source Sparrow frames are retained across the five main labels (12 each),
logo (15) and title Girlfriend (30), with 24 fps source sequences. Artwork is
resized proportionally and quantized to a shared 256-color bank palette; RLE is
lossless after that conversion. The 320x240 background is a centered 4:3 crop.
Nine banks total 340,944 bytes, excluding CD-sector allocation padding. Menu
banks are loaded before music and freed before loading gameplay; page navigation
performs no CD reads. Title/main texture-page reuse explicitly invalidates caches.

Main entries are Story Mode, Freeplay, Merch, Options and Credits. Credits use
the exact 0.8.4 credits JSON plus port attribution. The official backer-fetch
function returns an empty list in this release, so no names are invented.
Merch displays the official fallback shop address for another device. A stock
PS1 cannot reproduce the desktop browser action. Options still expose the
legacy port settings, not all official preferences, and do not persist to a card.

The actual menu state machine is exercised with controller/CD stubs under host
AddressSanitizer and UndefinedBehaviorSanitizer: wraparound, all five routes and
returns, stage selection, freeing menu banks, options, credits bounds, text bounds,
and rejecting a previously selected difficulty unsupported by the new song.
These tests do not emulate GPU, SPU, CD timing or controller hardware.

28 host tests pass. All eight source patches and the overlay apply to the clean
pinned upstream. The four new/replaced runtime modules compile with MIPS1 flags
and PsyQ headers. `preview_menu_art.py` reproduces the generated palette layout;
its image is a layout preview, not an emulator capture.

## Disc validation

Baseline CI at `5cfb13bb3be3a6c53f83a739523745ea4af03e7b` completed the full media
conversion, MIPS link and BIN/CUE build in run `34444744129`. Its disc contains
169,561 raw sectors (398,807,472 bytes), below the 333,000-sector budget. This
baseline predates the new menu runtime and does not contain complete 0.8.4 content.
Menu revision `5685efad0c0412fb823bc0aa55dac27235980ed5` also completed CI
(run `34595010476`): 169,740 raw sectors, 399,228,480 bytes. That build includes
the new menus but predates the 24 fps cutscene changes. Neither build establishes
emulator or real-console readiness.

## Complete-frame cutscene encoding

The pinned psxavenc revision is `82f3871c5fe5e82e71016a6636aba25ddddf2ca8`.
The local encoder patch drains buffered video after input EOF and tolerates
floating-point roundoff at frame boundaries. A 24-frame test previously produced
22 frames; the corrected encoder produces all 24. CI additionally tests 1- and
61-frame clips, complete STR sector/chunk sequences, and software MDEC decoding.

The converter uses a lossless FFV1/NUT intermediate with rational timestamps,
scales the 16:9 image proportionally to 320x180, and pads it to 320x240 with 30-pixel
bars. It encodes at 24 fps and 2x CD speed with 37.8 kHz stereo XA audio. These
are PS1-format conversions, not lossless copies of the original video/audio.

Local conversion and software MDEC decoding retain 2,074 Darnell, 684 2Hot and
1,051 Blazin frames. All three decoded completely. Reports include mean and
maximum quantization scale, dimensions, sector counts and source/decoded frame
counts. Console decoding and A/V timing remain unverified.

The STR player now displays the last prefetched frame, stops cleanly on an
unavailable next frame, avoids a squared timeout loop, rejects invalid/changing
frame dimensions, and clears its remembered dimensions between movies. Its
actual playback loop passes host sanitizer tests for 1-7 frames, truncated input,
skipping and malformed dimensions. These stubs do not simulate interrupt timing.
