# v0.8.4 Menu Foundation Checkpoint

Base: confirmed Erect/Nightmare audio checkpoint (`437b45838dbbc02947fd996fc0f0fd3077de69c2`).

Scope:
- Rebuild Freeplay around the v0.8.4 capsule/list presentation using PS1-native primitives.
- Keep Easy/Normal/Hard/Erect/Nightmare selection and per-song availability.
- Add a dedicated Character Select page and Freeplay -> Character Select -> Freeplay navigation.
- Remember selected Freeplay song, difficulty, and character for the current runtime session.
- Boyfriend is selectable.
- Pico is visible but intentionally locked until the Pico Mix checkpoint.
- Do not add Pico Mix charts/audio, Weekend 1, SPAGHETTI, or later content.

Validation gate:
- Compile PS-EXE.
- Build MODE2/2352 BIN/CUE.
- User validates menu navigation, difficulty selection, launching a BF song, returning/back navigation, and locked Pico behavior in DuckStation.
