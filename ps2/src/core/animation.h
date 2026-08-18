#ifndef FNF_PS2_ANIMATION_H
#define FNF_PS2_ANIMATION_H

#include "psx.h"
#include "fixed.h"

#define ASCR_REPEAT 0xFF
#define ASCR_CHGANI 0xFE
#define ASCR_BACK   0xFD

typedef struct Animation {
    u8 spd;
    const u8 *script;
} Animation;

typedef struct Animatable {
    const Animation *anims;
    const u8 *anim_p;
    u8 anim;
    fixed_t anim_time;
    fixed_t anim_spd;
    boolean ended;
} Animatable;

void Animatable_Init(Animatable *self, const Animation *anims);
void Animatable_SetAnim(Animatable *self, u8 anim);
void Animatable_Animate(Animatable *self, void *user, void (*set_frame)(void *, u8));
boolean Animatable_Ended(Animatable *self);

#endif
