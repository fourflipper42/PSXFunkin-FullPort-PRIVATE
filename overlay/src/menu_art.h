#ifndef MENU_ART_H
#define MENU_ART_H
#include "psx.h"
void MenuArt_Load(void);
void MenuArt_Free(void);
void MenuArt_Enter(void);
void MenuArt_Tick(int selected);
void MenuArt_Label(int item, int selected, int cx, int cy);
void MenuArt_Title(unsigned int song_ms);
void MenuArt_Back(void);
void MenuArt_Text(const char *text, int x, int y, int center, int bright);
unsigned int MenuArt_CreditCount(void);
const char *MenuArt_Credit(unsigned int line);
#endif
