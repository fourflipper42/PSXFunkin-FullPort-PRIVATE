#ifndef FNF_PS2_CAMERA_EFFECTS_H
#define FNF_PS2_CAMERA_EFFECTS_H

#include "fixed.h"
#include "rhythm.h"

typedef enum CameraEaseType {
    CAMERA_EASE_LINEAR = 0,
    CAMERA_EASE_SINE,
    CAMERA_EASE_QUAD,
    CAMERA_EASE_CUBE,
    CAMERA_EASE_QUART,
    CAMERA_EASE_QUINT,
    CAMERA_EASE_EXPO,
    CAMERA_EASE_SMOOTH_STEP,
    CAMERA_EASE_SMOOTHER_STEP,
    CAMERA_EASE_ELASTIC,
    CAMERA_EASE_BACK,
    CAMERA_EASE_BOUNCE,
    CAMERA_EASE_CIRC
} CameraEaseType;

typedef enum CameraEaseDir {
    CAMERA_EASE_IN = 0,
    CAMERA_EASE_OUT,
    CAMERA_EASE_IN_OUT
} CameraEaseDir;

typedef struct CameraEffects {
    float stage_zoom;
    float current_zoom;
    float tween_from;
    float tween_to;
    float tween_elapsed;
    float tween_duration;
    CameraEaseType tween_ease;
    CameraEaseDir tween_dir;
    boolean tween_active;

    float bop_intensity;
    float bop_rate;
    float bop_offset;
    float bop_multiplier;
    s32 last_bop_index;
} CameraEffects;

void CameraEffects_Init(CameraEffects *fx, float stage_zoom);
boolean CameraEffects_OnSongEvent(
    CameraEffects *fx,
    const RhythmState *rhythm,
    const char *name,
    const char *value_json);
void CameraEffects_Tick(
    CameraEffects *fx,
    const RhythmState *rhythm,
    s32 song_step,
    fixed_t dt);
float CameraEffects_Zoom(const CameraEffects *fx);

#endif
