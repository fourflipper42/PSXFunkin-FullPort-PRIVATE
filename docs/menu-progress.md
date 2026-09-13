# Menu fidelity checkpoint

Reference: official Funkin v0.8.4 source `90eabf0b38fd2fd79fbe88f1f37a0efe92052679`,
assets `d1d027d4747aaba151c6df121ea736c31d6aed38`.

## Implemented in this checkpoint

- Larger, uniformly scaled title logo and GF arranged for 320x240, retaining
  every source frame. The two GF dance halves alternate to the menu beat.
- All 45 idle and 8 confirm prompt frames, at 24 fps, split across two texture
  pages. Shared palettes prevent tile seams. Alpha is composited into the black
  title background before conversion so the idle fade survives PS1 cutout alpha.
- The original prompt still says Enter; a separate START / X hint identifies
  the actual controller inputs. A matching-lettering controller prompt remains
  necessary before claiming a fully adapted title.
- Title confirmation waits two seconds; another accept press skips ahead.
- Main menu retains all five original animated entries, follows selection with
  a camera, and uses the original 0.4 label / 0.17 background scroll factors.
  The background is cropped uniformly to 4:3 and overscanned to 384x288.
- Selected text flickers at 0.06 seconds, with the original magenta background
  flashing at 0.15 seconds. Navigation locks while confirmation is active.
- Official scroll, confirm and cancel sounds use 44.1 kHz SPU ADPCM. Sounds
  and art load before XA starts, and menu banks are released before gameplay.

## Still required

- White title flash and the original per-item alpha fade / exit transitions.
  Current page changes still use the base port's screen wipe after confirmation.
- Main-menu flashing preference and complete official settings behavior.
- Story Mode's character stage, week lettering and difficulty artwork.
- Official v0.8.4 Freeplay presentation, character selection, score/rank UI and
  transitions. Current Freeplay remains a functional text list.
- Original Options and Credits presentation and missing functionality.
- Compare emulator captures against the reference, including safe edges,
  frame pacing, SPU sound playback, VRAM residency and return from gameplay.
- Real-console testing. Host navigation tests and palette layout previews do
  not prove hardware correctness or visual parity.

## Verification and reproducibility

`python3 -m unittest discover -s tests -v` exercises the actual menu state machine
with hardware stubs, including confirmation timing, input lock, sound dispatch,
chart selection and no menu-navigation CD reads. Tile tests check retained
frames, repeated frames and cross-tile palette pixels.

`fetch_menu_assets.py`, `build_menu_art.py`, `build_menu_sound.py` and
`preview_menu_art.py` reproduce the pinned assets and review images. CI packages
`menu-preview.png` and `title-animation.gif` with its BIN/CUE artifact. These are
palette/layout previews, not emulator captures. This checkpoint's local artwork
banks total 577,824 bytes; the sound allocation ends at SPU address 85,056.

The last verified full disc before this checkpoint is commit
`3a3068fd5b8c5b732947aacb9209357081a60b0c` (504,426,384 bytes). A new CI run must
verify the checkpoint's linked memory and disc size before those numbers are
updated. Menus are **not finished** at this checkpoint.
