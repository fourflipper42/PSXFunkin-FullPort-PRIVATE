#include "timer.h"

u32 frame_count;
u32 animf_count;
fixed_t timer_sec;
fixed_t timer_dt;

void Timer_Init(void)
{
    frame_count = 0;
    animf_count = 0;
    timer_sec = 0;
    timer_dt = 0;
}

void Timer_Tick(void)
{
    fixed_t next_sec;

    ++frame_count;

    /*
     * The bootstrap renderer is VSync-paced at NTSC 60 Hz. Deriving time from
     * the frame count rather than repeatedly adding 1/60 avoids fixed-point
     * rounding drift. Song position will later come from the audio stream,
     * exactly where rhythm timing belongs.
     */
    next_sec = FIXED_DIV((fixed_t)frame_count, 60);
    timer_dt = next_sec - timer_sec;
    timer_sec = next_sec;
    animf_count = (timer_sec * 24) >> FIXED_SHIFT;
}

void Timer_Reset(void)
{
    Timer_Init();
}
