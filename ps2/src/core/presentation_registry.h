#ifndef FNF_PS2_PRESENTATION_REGISTRY_H
#define FNF_PS2_PRESENTATION_REGISTRY_H

#include "character.h"
#include "stage.h"

void PresentationRegistry_Reset(void);
void PresentationRegistry_RegisterStage(Stage *stage);
void PresentationRegistry_UnregisterStage(Stage *stage);
void PresentationRegistry_RegisterCharacter(Character *character);
void PresentationRegistry_UnregisterCharacter(Character *character);

Stage *PresentationRegistry_Stage(void);
Character *PresentationRegistry_Player(void);
Character *PresentationRegistry_Opponent(void);
Character *PresentationRegistry_Girlfriend(void);

#endif
