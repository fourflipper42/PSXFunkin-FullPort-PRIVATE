# Freeplay presentation checkpoint

Reference: Funkin v0.8.4 `90eabf0b38fd2fd79fbe88f1f37a0efe92052679` and
Funkin.assets `d1d027d4747aaba151c6df121ea736c31d6aed38`.

This replaces the old Freeplay text list with an initial BF presentation using
the original backing card, song panel, capsule artwork, DJ, difficulty graphics,
pixel icons and 5by7 font. It is not complete Freeplay parity.

Implemented:

- Uniformly scaled artwork composed for 320x240; no full-screen stretching.
- All 59 DJ frames across Intro (17), Idle (14) and Confirm (28), at 24 fps.
- All selected/unselected capsule frames and difficulty-art frames.
- All 68 icon idle/confirm frames in two static GPU atlases. Each song uses its
  character icon. The font uses monochrome rasterization to preserve thin strokes
  through PS1's binary transparency.
- Interpolated curved song positions and confirmation input lock. The selected
  supported chart launches after the DJ confirm sequence.
- Exclusive menu page ownership: stop XA, free old art, load the new page, then
  restart menu music. No disc reads, bank reloads or per-song allocation during
  scrolling or difficulty changes. Freeplay banks free before gameplay.
- Source-art assets total 587,951 bytes including transient TIM uploads, under
  the 850,000-byte page budget. The resident frame banks are smaller. The port
  retains a 1 MB heap; hardware peak usage still needs measurement.

Remaining:

- Song preview audio, Random, filters, favourites and sorting.
- Album display, real score/rank/completion widgets and capsule metadata.
- Character selection and Pico's matching presentation/playable variants.
- DJ AFK, TV, result reactions and unlock transitions. These source animations
  are explicitly listed as unimplemented in the build report; they were not
  decimated into the initial bank.
- Original shaders, dynamic background/transition layers and exact entrance /
  exit choreography. Current artwork includes a static 4:3 backing composition;
  page changes still use the port's wipe. Scrolling controls need hold-repeat.
- Emulator and real-PS1 review of animation cadence, GPU ordering, palette
  residency, sound playback and repeated gameplay returns.

Validation:

The host menu test exercises confirmation timing, chart selection, input lock,
exclusive art ownership and stopping XA before page loads. The preview compiles
`freeplay_art.c` and records its drawing calls before rendering the converted
palette pixels in reverse ordering-table order. This verifies actual renderer
positions/frame choices, not PS1 GPU behavior or performance.

CI runs `fetch_freeplay_assets.py`, `build_freeplay_art.py` and
`preview_freeplay.py`, checks the page budget, compiles the MIPS executable, checks
linked RAM/stack and CD size, and packages the PNG/GIF and asset report with the
BIN/CUE. Full-build validation for this checkpoint is pending until CI completes.
