#ifndef MENU_SOUND_H
#define MENU_SOUND_H
typedef enum { MenuSound_Scroll, MenuSound_Confirm, MenuSound_Cancel } MenuSound;
void MenuSound_Load(void);
void MenuSound_Free(void);
void MenuSound_Play(MenuSound sound);
#endif
