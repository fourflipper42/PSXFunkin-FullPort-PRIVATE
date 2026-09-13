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

Full CI run [34747965272](https://github.com/fourflipper42/PSXFunkin-FullPort-PRIVATE/actions/runs/34747965272)
passed at `15c8c5e83322e013e9cea72aa7abd2473e9f6d57`: 39 host tests, all media
conversion, MIPS compilation/link, RAM/stack validation and BIN/CUE packaging.
The disc is 504,802,704 bytes / 214,627 sectors, with 118,373 sectors remaining
within the 333,000-sector budget. Static memory ends at `0x80171a44`, leaving
582,844 bytes below the initial stack pointer (524,288 reserved).

The follow-up makes the IO word-buffer-to-byte-buffer cast explicit and corrects
the preview GIF's beat timing; it does not add menu functionality. Menus are
**not finished** at this checkpoint.

## Next Story Mode pass

Use `source/funkin/ui/story/StoryMenuState.hx` and the pinned
`preload/data/levels/*.json`, rather than the old port's list layout. The original
uses an upper character stage, scrolling week-title images, pink track text at
lower left, and an illustrated difficulty selector at lower right. Week 1's
background is `#F9CF51`; Weekend 1's is `#413CAE`. Character offsets, animation
prefixes and special confirmation offsets are supplied by each level JSON.

The base runtime has a 1 MB heap. Do not simply append all Story character banks
to the current title/main banks: measure their encoded sizes and implement page
asset lifetimes first. Preserve every animation frame. Any page/level CD reads
must explicitly coordinate with XA playback rather than seeking underneath it.
