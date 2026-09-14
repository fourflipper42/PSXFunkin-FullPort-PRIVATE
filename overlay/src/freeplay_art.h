#ifndef FREEPLAY_ART_H
#define FREEPLAY_ART_H
#include "fixed.h"
void FreeplayArt_Load(void);
void FreeplayArt_Free(void);
void FreeplayArt_State(int song, int filter, unsigned int favorites, int direction, fixed_t elapsed);
void FreeplayArt_Results(unsigned int score, unsigned int completion);
void FreeplayArt_UI(int difficulty, fixed_t elapsed);
void FreeplayArt_Back(int difficulty, fixed_t elapsed, int confirming, fixed_t confirm_elapsed);
void FreeplayArt_Song(const char *name, int song, int selected, fixed_t offset, fixed_t elapsed, fixed_t confirm_elapsed);
#endif
