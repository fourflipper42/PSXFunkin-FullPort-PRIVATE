#include "presentation_registry.h"

#include <string.h>

static Stage *g_stage;
static Character *g_player;
static Character *g_opponent;
static Character *g_girlfriend;
static u8 g_character_slot;

void PresentationRegistry_Reset(void)
{
    g_stage = NULL;
    g_player = NULL;
    g_opponent = NULL;
    g_girlfriend = NULL;
    g_character_slot = 0;
}

void PresentationRegistry_RegisterStage(Stage *stage)
{
    /* Stage is loaded before BF/Dad/GF in main.c, so it is the natural start
     * of a new presentation registration pass. */
    PresentationRegistry_Reset();
    g_stage = stage;
}

void PresentationRegistry_UnregisterStage(Stage *stage)
{
    if (g_stage == stage)
        g_stage = NULL;
    if (g_stage == NULL && g_player == NULL && g_opponent == NULL && g_girlfriend == NULL)
        g_character_slot = 0;
}

void PresentationRegistry_RegisterCharacter(Character *character)
{
    /* Role assignment follows main.c's fixed load order. Advance even when a
     * character asset fails so Dad/GF cannot slide into the wrong role. */
    switch (g_character_slot) {
        case 0: g_player = character; break;
        case 1: g_opponent = character; break;
        case 2: g_girlfriend = character; break;
        default: break;
    }
    if (g_character_slot < 0xFFu)
        ++g_character_slot;
}

void PresentationRegistry_UnregisterCharacter(Character *character)
{
    if (g_player == character) g_player = NULL;
    if (g_opponent == character) g_opponent = NULL;
    if (g_girlfriend == character) g_girlfriend = NULL;
    if (g_stage == NULL && g_player == NULL && g_opponent == NULL && g_girlfriend == NULL)
        g_character_slot = 0;
}

Stage *PresentationRegistry_Stage(void) { return g_stage; }
Character *PresentationRegistry_Player(void) { return g_player; }
Character *PresentationRegistry_Opponent(void) { return g_opponent; }
Character *PresentationRegistry_Girlfriend(void) { return g_girlfriend; }
