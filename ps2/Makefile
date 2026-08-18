EE_BIN = build/funkin_ps2.elf
EE_OBJS = \
	build/main.o \
	build/core_timer.o \
	build/core_animation.o \
	build/core_random.o \
	build/core_mem.o \
	build/core_object.o \
	build/core_chart.o \
	build/core_chart_asset.o \
	build/core_rhythm.o \
	build/core_pad.o \
	build/core_audio.o \
	build/core_disc.o \
	build/core_asset_file.o \
	build/core_song_catalog.o \
	build/core_story_catalog.o \
	build/core_story_session.o \
	build/core_progression.o \
	build/core_save_data.o \
	build/core_ps2_glyph.o \
	build/core_better_alphabet.o \
	build/core_song_descriptor.o \
	build/core_song_events.o \
	build/core_note_kinds.o \
	build/core_note_kind_runtime.o \
	build/core_song_stream.o \
	build/core_gameplay.o \
	build/core_gameplay_scroll.o \
	build/core_gammod.o \
	build/core_endless_mode.o \
	build/core_combo_system.o \
	build/core_camera_effects.o \
	build/core_camera_movement.o \
	build/core_presentation_events.o \
	build/core_pointless_pins.o \
	build/core_session_runtime.o \
	build/core_freeplay_browser.o \
	build/core_frontend.o \
	build/core_texture_asset.o \
	build/core_sprite_atlas.o \
	build/core_note_style.o \
	build/core_note_lane_renderer.o \
	build/core_health_icon.o \
	build/core_hud.o \
	build/core_character.o \
	build/core_stage.o \
	build/audsrv_irx.o

EE_INCS += -I$(GSKIT)/include -Isrc -Isrc/core
EE_LDFLAGS += -L$(GSKIT)/lib
EE_LIBS = -lgskit -ldmakit -lpad -lmc -laudsrv -lpatches -lcdvd -ldebug -lm -lc

EE_CFLAGS += -O2 -G0 -Wall -Wextra -Wno-unused-parameter -DFNF_PS2

.PHONY: all clean run

all: $(EE_BIN)

build:
	mkdir -p build

$(EE_BIN): | build

build/main.o: src/main.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_timer.o: src/core/timer.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_animation.o: src/core/animation.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_random.o: src/core/random.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_mem.o: src/core/mem.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_object.o: src/core/object.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_chart.o: src/core/chart.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_chart_asset.o: src/core/chart_asset.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_rhythm.o: src/core/rhythm.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_pad.o: src/core/pad.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_audio.o: src/core/audio.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_disc.o: src/core/disc.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_asset_file.o: src/core/asset_file.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_song_catalog.o: src/core/song_catalog.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_story_catalog.o: src/core/story_catalog.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_story_session.o: src/core/story_session.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_progression.o: src/core/progression.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_save_data.o: src/core/save_data.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_ps2_glyph.o: src/core/ps2_glyph.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_better_alphabet.o: src/core/better_alphabet.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_song_descriptor.o: src/core/song_descriptor.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_song_events.o: src/core/song_events.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_note_kinds.o: src/core/note_kinds.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_note_kind_runtime.o: src/core/note_kind_runtime.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_song_stream.o: src/core/song_stream.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_gameplay.o: src/core/gameplay.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_gameplay_scroll.o: src/core/gameplay_scroll.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_gammod.o: src/core/gammod.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_endless_mode.o: src/core/endless_mode.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_combo_system.o: src/core/combo_system.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_camera_effects.o: src/core/camera_effects.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_camera_movement.o: src/core/camera_movement.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_presentation_events.o: src/core/presentation_events.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_pointless_pins.o: src/core/pointless_pins.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_session_runtime.o: src/core/session_runtime.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_freeplay_browser.o: src/core/freeplay_browser.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_frontend.o: src/core/frontend.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_texture_asset.o: src/core/texture_asset.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_sprite_atlas.o: src/core/sprite_atlas.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_note_style.o: src/core/note_style.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_note_lane_renderer.o: src/core/note_lane_renderer.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_health_icon.o: src/core/health_icon.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_hud.o: src/core/hud.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_character.o: src/core/character.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_stage.o: src/core/stage.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/audsrv_irx.c: | build
	$(PS2SDK)/bin/bin2c $(PS2SDK)/iop/irx/audsrv.irx $@ audsrv_irx

build/audsrv_irx.o: build/audsrv_irx.c
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

clean:
	rm -rf build

run: $(EE_BIN)
	ps2client execee host:$(EE_BIN)

include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
