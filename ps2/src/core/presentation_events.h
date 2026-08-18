#ifndef FNF_PS2_PRESENTATION_EVENTS_H
#define FNF_PS2_PRESENTATION_EVENTS_H

#include "camera_effects.h"
#include "character.h"
#include "gameplay.h"
#include "stage.h"

typedef struct PresentationEventTargets {
    CameraEffects *camera;
    RhythmState *rhythm;
    Character *player;
    Character *opponent;
    Character *girlfriend;
    Stage *stage;
} PresentationEventTargets;

boolean PresentationEvents_Handle(
    PresentationEventTargets *targets,
    const GameplaySongEventFrame *event);

#endif
