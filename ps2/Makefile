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
	build/core_song_stream.o \
	build/core_gameplay.o \
	build/audsrv_irx.o

EE_INCS += -I$(GSKIT)/include -Isrc -Isrc/core
EE_LDFLAGS += -L$(GSKIT)/lib
EE_LIBS = -lgskit -ldmakit -lpad -laudsrv -lpatches -lcdvd -ldebug -lc

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

build/core_song_stream.o: src/core/song_stream.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

build/core_gameplay.o: src/core/gameplay.c | build
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
