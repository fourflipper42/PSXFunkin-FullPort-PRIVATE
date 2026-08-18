#ifndef FNF_PS2_TIMER_H
#define FNF_PS2_TIMER_H

#include "fixed.h"

extern u32 frame_count;
extern u32 animf_count;
extern fixed_t timer_sec;
extern fixed_t timer_dt;
/* Presentation-only delta. Reset to timer_dt each frame, then gameplay mods
 * may scale it before character/stage animation ticks run. */
extern fixed_t timer_presentation_dt;

void Timer_Init(void);
void Timer_Tick(void);
void Timer_Reset(void);

#endif
