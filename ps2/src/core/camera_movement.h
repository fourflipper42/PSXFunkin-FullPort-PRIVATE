#ifndef FNF_PS2_CAMERA_MOVEMENT_H
#define FNF_PS2_CAMERA_MOVEMENT_H

#include "fixed.h"

typedef struct CameraMovement {
    float offset_x;
    float offset_y;
    float target_x;
    float target_y;
    float intensity;
    boolean enabled;
    boolean only_player;
} CameraMovement;

void CameraMovement_Init(CameraMovement *movement);
void CameraMovement_Configure(
    CameraMovement *movement,
    boolean enabled,
    boolean only_player,
    float intensity);
void CameraMovement_OnNoteHit(
    CameraMovement *movement,
    u8 lane,
    boolean opponent);
void CameraMovement_Tick(CameraMovement *movement);
float CameraMovement_X(const CameraMovement *movement);
float CameraMovement_Y(const CameraMovement *movement);

#endif
