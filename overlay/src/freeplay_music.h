#ifndef FREEPLAY_MUSIC_H
#define FREEPLAY_MUSIC_H
#include "fixed.h"
void FreeplayMusic_Load(void);
void FreeplayMusic_Tick(int song,int difficulty,fixed_t dt,int enabled);
#endif
