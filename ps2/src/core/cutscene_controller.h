#ifndef FNF_PS2_CUTSCENE_CONTROLLER_H
#define FNF_PS2_CUTSCENE_CONTROLLER_H

#include "cutscene_map.h"
#include "cutscene_stream.h"
#include "pad.h"

boolean CutsceneController_Init(void);
void CutsceneController_Shutdown(void);
void CutsceneController_ResetStory(void);
boolean CutsceneController_BeginSong(
    GSGLOBAL *gs,
    const char *song_id,
    boolean story_mode);
void CutsceneController_HandlePad(const Pad *pad);
void CutsceneController_Tick(void);
void CutsceneController_Draw(GSGLOBAL *gs);
boolean CutsceneController_Active(void);

#endif
