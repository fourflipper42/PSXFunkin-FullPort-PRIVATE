EE_BIN = build/funkin_ps2.elf
EE_OBJS = build/main.o

EE_INCS += -I$(GSKIT)/include -Isrc
EE_LDFLAGS += -L$(GSKIT)/lib
EE_LIBS = -lgskit -ldmakit -lpad -ldebug -lc

EE_CFLAGS += -O2 -G0 -Wall -Wextra -Wno-unused-parameter -DFNF_PS2

.PHONY: all clean run

all: $(EE_BIN)

build:
	mkdir -p build

build/main.o: src/main.c | build
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -c $< -o $@

$(EE_BIN): $(EE_OBJS)
	$(EE_CC) $(EE_CFLAGS) -T$(PS2SDK)/ee/startup/linkfile $(EE_LDFLAGS) -o $@ $(EE_OBJS) $(EE_LIBS)

clean:
	rm -rf build

run: $(EE_BIN)
	ps2client execee host:$(EE_BIN)

include $(PS2SDK)/samples/Makefile.pref
