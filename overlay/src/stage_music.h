#ifndef STAGE_MUSIC_H
#define STAGE_MUSIC_H
#include "stage.h"

/* CD routing and scroll speed for the selected chart variation. */
fixed_t StageMusic_Speed(StageId id, StageDiff difficulty, fixed_t fallback);
void StageMusic_Load(Stage *state);
#endif
