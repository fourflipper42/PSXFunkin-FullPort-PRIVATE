#ifndef FNF_PS2_PAD_H
#define FNF_PS2_PAD_H

#include "psx.h"
#include <libpad.h>

typedef struct Pad {
    u16 held;
    u16 press;
    u8 left_x;
    u8 left_y;
    u8 right_x;
    u8 right_y;
} Pad;

extern Pad pad_state;

void Pad_Init(void);
void Pad_Update(void);
boolean Pad_Ready(void);

#endif
