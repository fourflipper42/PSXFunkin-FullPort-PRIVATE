#include "camera_movement.h"

#include <string.h>

void CameraMovement_Init(CameraMovement *movement)
{
    if (movement == NULL)
        return;
    memset(movement, 0, sizeof(*movement));
    movement->enabled = true;
    movement->intensity = 80.0f;
}

void CameraMovement_Configure(
    CameraMovement *movement,
    boolean enabled,
    boolean only_player,
    float intensity)
{
    if (movement == NULL)
        return;
    movement->enabled = enabled;
    movement->only_player = only_player;
    if (intensity < 20.0f) intensity = 20.0f;
    if (intensity > 150.0f) intensity = 150.0f;
    movement->intensity = intensity;
    if (!enabled) {
        movement->target_x = 0.0f;
        movement->target_y = 0.0f;
    }
}

void CameraMovement_OnNoteHit(
    CameraMovement *movement,
    u8 lane,
    boolean opponent)
{
    if (movement == NULL || !movement->enabled ||
        (movement->only_player && opponent))
        return;

    movement->target_x = 0.0f;
    movement->target_y = 0.0f;
    switch (lane & 3) {
        case 0: movement->target_x = -movement->intensity; break;
        case 1: movement->target_y = movement->intensity; break;
        case 2: movement->target_y = -movement->intensity; break;
        case 3: movement->target_x = movement->intensity; break;
    }
}

void CameraMovement_Tick(CameraMovement *movement)
{
    if (movement == NULL)
        return;
    movement->offset_x += (movement->target_x - movement->offset_x) * 0.20f;
    movement->offset_y += (movement->target_y - movement->offset_y) * 0.20f;
}

float CameraMovement_X(const CameraMovement *movement)
{
    return movement != NULL ? movement->offset_x : 0.0f;
}

float CameraMovement_Y(const CameraMovement *movement)
{
    return movement != NULL ? movement->offset_y : 0.0f;
}
