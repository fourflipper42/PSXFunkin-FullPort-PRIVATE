#ifndef FNF_PS2_WEEKEND1_VISUAL_H
#define FNF_PS2_WEEKEND1_VISUAL_H

#include "stage.h"

void Weekend1Visual_Begin2Hot(void);
void Weekend1Visual_End(void);
void Weekend1Visual_KickCan(void);
void Weekend1Visual_ShootCan(void);
void Weekend1Visual_ImpactCan(void);
void Weekend1Visual_Tick(fixed_t elapsed);
void Weekend1Visual_DrawRange(
    GSGLOBAL *gs,
    const Stage *stage,
    const StageCamera *camera,
    s32 z_min,
    s32 z_max);

#endif
