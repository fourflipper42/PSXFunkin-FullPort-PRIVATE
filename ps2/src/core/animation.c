#include "animation.h"
#include "timer.h"

void Animatable_Init(Animatable *self, const Animation *anims)
{
    self->anims = anims;
}

void Animatable_SetAnim(Animatable *self, u8 anim)
{
    self->anim = anim;
    self->anim_p = self->anims[anim].script;
    self->anim_spd = FIXED_DEC(self->anims[anim].spd, 1) / 24;
    self->anim_time = 0;
    self->ended = false;
}

void Animatable_Animate(Animatable *self, void *user, void (*set_frame)(void *, u8))
{
    self->anim_time -= timer_dt;

    while (self->anim_time <= 0) {
        switch (self->anim_p[0]) {
            case ASCR_REPEAT:
                self->anim_p = self->anims[self->anim].script;
                self->ended = true;
                break;

            case ASCR_CHGANI:
                Animatable_SetAnim(self, self->anim_p[1]);
                break;

            case ASCR_BACK:
                self->anim_time += self->anim_spd;
                self->anim_p -= self->anim_p[1];
                self->ended = true;
                break;

            default:
                set_frame(user, self->anim_p[0]);
                self->anim_time += self->anim_spd;
                ++self->anim_p;
                break;
        }
    }
}

boolean Animatable_Ended(Animatable *self)
{
    return self->ended;
}
