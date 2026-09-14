# Freeplay presentation checkpoint

Reference: Funkin v0.8.4 `90eabf0b38fd2fd79fbe88f1f37a0efe92052679` and
Funkin.assets `d1d027d4747aaba151c6df121ea736c31d6aed38`.

This replaces the old Freeplay text list with a BF presentation using
the original backing card, song panel, capsule artwork, DJ, difficulty graphics,
pixel icons and 5by7 font. It is not complete Freeplay parity.

Implemented:

- Uniformly scaled artwork composed for 320x240; no full-screen stretching.
  BF and his turntable are placed 35 pixels lower following user review.
  The supplied reference now guides the whole composition: 142px capsules form
  a narrower central column, Tutorial sits beside BF's head, and the lower songs
  sit alongside the turntable. The right side is reserved for album/score UI.
- All 59 DJ frames across Intro (17), Idle (14) and Confirm (28), at 24 fps.
- All selected/unselected capsule frames and difficulty-art frames.
- Original 15-frame difficulty arrows, mirrored on the right, including the
  white half-size press response lasting 2/24 seconds.
- Animated original filter symbols: L1/R1 cycles #, favourites, ALL and the
  official letter ranges. The selected symbol retains all 56 frames. Alphabet
  filters sort their songs; favourites keep week order. Square toggles a song's
  favourite status. Empty filters cannot launch an unrelated Random song.
- Six original album covers and animated titles. All 186 cover timeline frames
  and every title frame are retained. Album, BPM and difficulty ratings come
  from pinned metadata, including the different Erect/Nightmare metadata.
- Original high-score art and seven score digits, clear percentage, capsule
  BPM/rating numbers, week labels, favourite hearts, VCR header font and scrolling
  backing text. BF's approved lower position is unchanged.
- Completed gameplay runs feed session high scores and completion percentages.
  Completion uses the official `(sick + good - missed) / totalNotes` formula;
  aborted runs do not replace records. The underlying port's scoring/judgement
  rules still differ from official Funkin. Records and favourites currently
  survive gameplay/menu returns but do not persist to a memory card.
- All 74 icon idle/confirm frames in two static GPU atlases. Each song uses its
  character icon. The font uses monochrome rasterization to preserve thin strokes
  through PS1's binary transparency.
- Interpolated curved song positions and confirmation input lock. The selected
  supported chart launches after the DJ confirm sequence.
- Random is the first entry and selects uniformly among charts supporting the
  chosen difficulty. Long titles scroll within the capsule's text window.
- Exclusive menu page ownership: stop XA, free old art, load the new page, then
  restart menu music. No disc reads, bank reloads or per-song allocation during
  scrolling or difficulty changes. Freeplay banks free before gameplay.
- Hold-to-scroll has a 400ms initial delay and 100ms repeats, stopping on release.
- Disc artwork totals 1,116,814 bytes. Sector-rounded resident banks plus
  allocator allowance total 774,400 bytes; adding the largest transient TIM
  gives an estimated 842,016-byte art peak, below the unchanged 850,000-byte
  page allocation budget. TIMs free after GPU upload. The 1 MB heap leaves room
  for other menu allocations; hardware peak usage still needs measurement.

Remaining:

- Instrumental song preview audio and its seek/fade behaviour.
- Memory-card persistence, rank badges, difficulty stars/flames, favourite sound
  effects, score interpolation and remaining capsule entrance/highlight effects.
- Character selection and Pico's matching presentation/playable variants.
- DJ AFK, TV, result reactions and unlock transitions. These source animations
  are explicitly listed as unimplemented in the build report; they were not
  decimated into the initial bank.
- Original shaders, dynamic background/transition layers and exact entrance /
  exit choreography. Current artwork includes a static 4:3 backing composition;
  page changes still use the port's wipe. The scrolling backing text is now
  present, but the additive glows and original layered transitions are not.
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
BIN/CUE. Full CI [34763683714](https://github.com/fourflipper42/PSXFunkin-FullPort-PRIVATE/actions/runs/34763683714)
passed at `41f45d3cc2635ab50852757e157c1d81d0e86397`: all 39 host tests, asset and
media conversion, MIPS compilation/link, RAM/stack checks and disc packaging.
The disc is 505,498,896 bytes / 214,923 sectors, leaving 118,077 sectors within
the 333,000-sector budget. Static memory ends at `0x80172c04`; 578,300 bytes remain
below the initial stack pointer, including the 524,288-byte stack reserve.

The earlier follow-up reflows the composition using the supplied reference, adds Random,
corrects Tutorial's icon, and corrects preview sampling to retain all 59 DJ frames
at 24fps average GIF timing. The actual C renderer preview and 39 host tests pass,
including Random's difficulty filtering. Full-build numbers above refer to the
initial checkpoint, before that follow-up. Its full CI 34781131104 subsequently
passed at `7096b715e25d14c0b423e5873fdb6f0bd2867da9`.

The current widget/results follow-up passes 42 host tests, including filter and
empty-Random behaviour, hold-repeat, completed-run records and native frame-bank
uploads below the top of a texture page. The results patch applies against the
preceding stage source and Makefile patches. The actual C renderer produces a
PNG/GIF and a six-state contact sheet covering all difficulties, arrow feedback,
an explicitly labelled example score and Weekend 1. Full CI for this follow-up
must be checked separately. These previews do not emulate PS1 GPU/CD timing.
