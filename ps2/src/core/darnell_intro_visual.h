#ifndef FNF_PS2_DARNELL_INTRO_VISUAL_H
#define FNF_PS2_DARNELL_INTRO_VISUAL_H

#include "stage.h"

void DarnellIntroVisual_SetSong(const char *song_id);
void DarnellIntroVisual_AutoTick(fixed_t elapsed);
void DarnellIntroVisual_Begin(void);
void DarnellIntroVisual_End(void);
void DarnellIntroVisual_KickUp(void);
void DarnellIntroVisual_KneeForward(void);
void DarnellIntroVisual_Shoot(void);
void DarnellIntroVisual_Tick(fixed_t elapsed);
void DarnellIntroVisual_DrawRange(
    GSGLOBAL *gs,
    const Stage *stage,
    const StageCamera *camera,
    s32 z_min,
    s32 z_max);

#endif
