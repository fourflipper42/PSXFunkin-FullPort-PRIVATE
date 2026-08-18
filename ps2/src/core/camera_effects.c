#include "camera_effects.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

#define CAMERA_DEFAULT_BOP_INTENSITY 1.015f
#define CAMERA_DEFAULT_BOP_RATE 4.0f
#define CAMERA_DEFAULT_BOP_OFFSET 0.0f
#define CAMERA_DEFAULT_ZOOM_DURATION_STEPS 4.0f
#define CAMERA_PI 3.14159265358979323846f

static float clamp01(float value)
{
    if (value < 0.0f)
        return 0.0f;
    if (value > 1.0f)
        return 1.0f;
    return value;
}

static const char *skip_space(const char *text)
{
    while (text != NULL && (*text == ' ' || *text == '\t' || *text == '\r' || *text == '\n'))
        ++text;
    return text;
}

static const char *json_value(const char *json, const char *key)
{
    char needle[64];
    const char *found;
    const char *colon;
    size_t key_len;

    if (json == NULL || key == NULL)
        return NULL;
    key_len = strlen(key);
    if (key_len + 3u >= sizeof(needle))
        return NULL;

    needle[0] = '"';
    memcpy(needle + 1, key, key_len);
    needle[key_len + 1] = '"';
    needle[key_len + 2] = '\0';

    found = strstr(json, needle);
    if (found == NULL)
        return NULL;
    colon = strchr(found + key_len + 2, ':');
    if (colon == NULL)
        return NULL;
    return skip_space(colon + 1);
}

static float json_number(const char *json, const char *key, float fallback)
{
    const char *value = json_value(json, key);
    char *end;
    float parsed;

    if (value == NULL)
        return fallback;
    parsed = strtof(value, &end);
    if (end == value)
        return fallback;
    return parsed;
}

static float json_scalar_number(const char *json, float fallback)
{
    const char *value = skip_space(json);
    char *end;
    float parsed;

    if (value == NULL || *value == '{' || *value == '[' || *value == '"')
        return fallback;
    parsed = strtof(value, &end);
    if (end == value)
        return fallback;
    return parsed;
}

static boolean json_string(
    const char *json,
    const char *key,
    char *out,
    size_t out_size,
    const char *fallback)
{
    const char *value;
    const char *end;
    size_t length;

    if (out == NULL || out_size == 0)
        return false;
    out[0] = '\0';

    value = json_value(json, key);
    if (value == NULL || *value != '"') {
        if (fallback != NULL) {
            strncpy(out, fallback, out_size - 1);
            out[out_size - 1] = '\0';
        }
        return false;
    }

    ++value;
    end = value;
    while (*end != '\0' && *end != '"') {
        if (*end == '\\' && end[1] != '\0')
            ++end;
        ++end;
    }
    length = (size_t)(end - value);
    if (length >= out_size)
        length = out_size - 1;
    memcpy(out, value, length);
    out[length] = '\0';
    return true;
}

static boolean ends_with(const char *text, const char *suffix)
{
    size_t text_len;
    size_t suffix_len;
    if (text == NULL || suffix == NULL)
        return false;
    text_len = strlen(text);
    suffix_len = strlen(suffix);
    return text_len >= suffix_len && strcmp(text + text_len - suffix_len, suffix) == 0;
}

static void parse_ease(const char *json, CameraEaseType *type, CameraEaseDir *dir, boolean *instant)
{
    char ease[32];
    char ease_dir[16];
    size_t len;

    *type = CAMERA_EASE_LINEAR;
    *dir = CAMERA_EASE_IN;
    *instant = false;

    json_string(json, "ease", ease, sizeof(ease), "linear");
    json_string(json, "easeDir", ease_dir, sizeof(ease_dir), "In");

    if (strcmp(ease, "INSTANT") == 0) {
        *instant = true;
        return;
    }

    if (ends_with(ease, "InOut")) {
        *dir = CAMERA_EASE_IN_OUT;
        len = strlen(ease);
        ease[len - 5] = '\0';
    } else if (ends_with(ease, "Out")) {
        *dir = CAMERA_EASE_OUT;
        len = strlen(ease);
        ease[len - 3] = '\0';
    } else if (ends_with(ease, "In") && strcmp(ease, "linear") != 0) {
        *dir = CAMERA_EASE_IN;
        len = strlen(ease);
        ease[len - 2] = '\0';
    } else if (strcmp(ease_dir, "Out") == 0) {
        *dir = CAMERA_EASE_OUT;
    } else if (strcmp(ease_dir, "InOut") == 0) {
        *dir = CAMERA_EASE_IN_OUT;
    }

    if (strcmp(ease, "sine") == 0) *type = CAMERA_EASE_SINE;
    else if (strcmp(ease, "quad") == 0) *type = CAMERA_EASE_QUAD;
    else if (strcmp(ease, "cube") == 0) *type = CAMERA_EASE_CUBE;
    else if (strcmp(ease, "quart") == 0) *type = CAMERA_EASE_QUART;
    else if (strcmp(ease, "quint") == 0) *type = CAMERA_EASE_QUINT;
    else if (strcmp(ease, "expo") == 0) *type = CAMERA_EASE_EXPO;
    else if (strcmp(ease, "smoothStep") == 0) *type = CAMERA_EASE_SMOOTH_STEP;
    else if (strcmp(ease, "smootherStep") == 0) *type = CAMERA_EASE_SMOOTHER_STEP;
    else if (strcmp(ease, "elastic") == 0) *type = CAMERA_EASE_ELASTIC;
    else if (strcmp(ease, "back") == 0) *type = CAMERA_EASE_BACK;
    else if (strcmp(ease, "bounce") == 0) *type = CAMERA_EASE_BOUNCE;
    else if (strcmp(ease, "circ") == 0) *type = CAMERA_EASE_CIRC;
}

static float ease_in(CameraEaseType type, float t)
{
    const float back_c1 = 1.70158f;
    const float back_c3 = back_c1 + 1.0f;

    switch (type) {
        case CAMERA_EASE_SINE:
            return 1.0f - cosf((t * CAMERA_PI) * 0.5f);
        case CAMERA_EASE_QUAD:
            return t * t;
        case CAMERA_EASE_CUBE:
            return t * t * t;
        case CAMERA_EASE_QUART:
            return t * t * t * t;
        case CAMERA_EASE_QUINT:
            return t * t * t * t * t;
        case CAMERA_EASE_EXPO:
            return t <= 0.0f ? 0.0f : powf(2.0f, 10.0f * t - 10.0f);
        case CAMERA_EASE_SMOOTH_STEP:
            return t * t * (3.0f - 2.0f * t);
        case CAMERA_EASE_SMOOTHER_STEP:
            return t * t * t * (t * (t * 6.0f - 15.0f) + 10.0f);
        case CAMERA_EASE_ELASTIC:
            if (t <= 0.0f || t >= 1.0f) return t;
            return -powf(2.0f, 10.0f * t - 10.0f) *
                sinf((t * 10.0f - 10.75f) * ((2.0f * CAMERA_PI) / 3.0f));
        case CAMERA_EASE_BACK:
            return back_c3 * t * t * t - back_c1 * t * t;
        case CAMERA_EASE_CIRC:
            return 1.0f - sqrtf(1.0f - t * t);
        case CAMERA_EASE_BOUNCE:
        case CAMERA_EASE_LINEAR:
        default:
            return t;
    }
}

static float bounce_out(float t)
{
    const float n1 = 7.5625f;
    const float d1 = 2.75f;
    if (t < 1.0f / d1)
        return n1 * t * t;
    if (t < 2.0f / d1) {
        t -= 1.5f / d1;
        return n1 * t * t + 0.75f;
    }
    if (t < 2.5f / d1) {
        t -= 2.25f / d1;
        return n1 * t * t + 0.9375f;
    }
    t -= 2.625f / d1;
    return n1 * t * t + 0.984375f;
}

static float apply_ease(CameraEaseType type, CameraEaseDir dir, float t)
{
    float half;
    t = clamp01(t);

    if (type == CAMERA_EASE_LINEAR)
        return t;
    if (type == CAMERA_EASE_BOUNCE) {
        if (dir == CAMERA_EASE_OUT)
            return bounce_out(t);
        if (dir == CAMERA_EASE_IN)
            return 1.0f - bounce_out(1.0f - t);
        if (t < 0.5f)
            return (1.0f - bounce_out(1.0f - 2.0f * t)) * 0.5f;
        return (1.0f + bounce_out(2.0f * t - 1.0f)) * 0.5f;
    }

    if (dir == CAMERA_EASE_OUT)
        return 1.0f - ease_in(type, 1.0f - t);
    if (dir == CAMERA_EASE_IN_OUT) {
        if (t < 0.5f) {
            half = ease_in(type, t * 2.0f);
            return half * 0.5f;
        }
        half = ease_in(type, (1.0f - t) * 2.0f);
        return 1.0f - half * 0.5f;
    }
    return ease_in(type, t);
}

static float step_seconds(const RhythmState *rhythm)
{
    float scroll_per_second;
    if (rhythm == NULL || rhythm->step_crochet <= 0)
        return 0.125f;
    scroll_per_second = (float)rhythm->step_crochet / (float)FIXED_UNIT;
    if (scroll_per_second <= 0.0f)
        return 0.125f;
    return 12.0f / scroll_per_second;
}

void CameraEffects_Init(CameraEffects *fx, float stage_zoom)
{
    if (fx == NULL)
        return;
    memset(fx, 0, sizeof(*fx));
    if (stage_zoom <= 0.0f)
        stage_zoom = 1.0f;
    fx->stage_zoom = stage_zoom;
    fx->current_zoom = stage_zoom;
    fx->tween_from = stage_zoom;
    fx->tween_to = stage_zoom;
    fx->bop_intensity = CAMERA_DEFAULT_BOP_INTENSITY;
    fx->bop_rate = CAMERA_DEFAULT_BOP_RATE;
    fx->bop_offset = CAMERA_DEFAULT_BOP_OFFSET;
    fx->bop_multiplier = 1.0f;
    fx->last_bop_index = -0x7fffffff;
}

boolean CameraEffects_OnSongEvent(
    CameraEffects *fx,
    const RhythmState *rhythm,
    const char *name,
    const char *value_json)
{
    if (fx == NULL || name == NULL || value_json == NULL)
        return false;

    if (strcmp(name, "ZoomCamera") == 0) {
        char mode[16];
        CameraEaseType ease;
        CameraEaseDir dir;
        boolean instant;
        float zoom;
        float duration_steps;
        float duration_seconds;

        if (*skip_space(value_json) == '{')
            zoom = json_number(value_json, "zoom", 1.0f);
        else
            zoom = json_scalar_number(value_json, 1.0f);
        duration_steps = json_number(
            value_json,
            "duration",
            CAMERA_DEFAULT_ZOOM_DURATION_STEPS);
        json_string(value_json, "mode", mode, sizeof(mode), "direct");
        parse_ease(value_json, &ease, &dir, &instant);

        fx->tween_from = fx->current_zoom;
        fx->tween_to = strcmp(mode, "stage") == 0 ? fx->stage_zoom * zoom : zoom;
        if (fx->tween_to <= 0.0f)
            fx->tween_to = 0.01f;
        duration_seconds = step_seconds(rhythm) * duration_steps;
        if (instant || duration_seconds <= 0.0f) {
            fx->current_zoom = fx->tween_to;
            fx->tween_active = false;
        } else {
            fx->tween_elapsed = 0.0f;
            fx->tween_duration = duration_seconds;
            fx->tween_ease = ease;
            fx->tween_dir = dir;
            fx->tween_active = true;
        }
        return true;
    }

    if (strcmp(name, "SetCameraBop") == 0) {
        float intensity = json_number(value_json, "intensity", 1.0f);
        fx->bop_intensity =
            (CAMERA_DEFAULT_BOP_INTENSITY - 1.0f) * intensity + 1.0f;
        fx->bop_rate = json_number(value_json, "rate", CAMERA_DEFAULT_BOP_RATE);
        fx->bop_offset = json_number(value_json, "offset", CAMERA_DEFAULT_BOP_OFFSET);
        if (fx->bop_rate < 0.25f)
            fx->bop_rate = 0.25f;
        fx->last_bop_index = -0x7fffffff;
        return true;
    }

    return false;
}

void CameraEffects_Tick(
    CameraEffects *fx,
    const RhythmState *rhythm,
    s32 song_step,
    fixed_t dt)
{
    float seconds;
    float rate_steps;
    float offset_steps;
    float phase;
    s32 bop_index;
    float decay;

    (void)rhythm;
    if (fx == NULL)
        return;

    seconds = (float)dt / (float)FIXED_UNIT;
    if (seconds < 0.0f)
        seconds = 0.0f;

    if (fx->tween_active) {
        float progress;
        float eased;
        fx->tween_elapsed += seconds;
        progress = fx->tween_duration > 0.0f
            ? fx->tween_elapsed / fx->tween_duration
            : 1.0f;
        if (progress >= 1.0f) {
            fx->current_zoom = fx->tween_to;
            fx->tween_active = false;
        } else {
            eased = apply_ease(fx->tween_ease, fx->tween_dir, progress);
            fx->current_zoom = fx->tween_from +
                (fx->tween_to - fx->tween_from) * eased;
        }
    }

    if (song_step >= 0) {
        rate_steps = fx->bop_rate * 4.0f;
        offset_steps = fx->bop_offset * 4.0f;
        if (rate_steps < 1.0f)
            rate_steps = 1.0f;
        phase = ((float)song_step - offset_steps) / rate_steps;
        if (phase >= 0.0f) {
            bop_index = (s32)floorf(phase + 0.0001f);
            if (bop_index != fx->last_bop_index) {
                fx->last_bop_index = bop_index;
                fx->bop_multiplier = fx->bop_intensity;
            }
        }
    }

    decay = seconds * 3.125f;
    if (decay > 1.0f)
        decay = 1.0f;
    fx->bop_multiplier += (1.0f - fx->bop_multiplier) * decay;
}

float CameraEffects_Zoom(const CameraEffects *fx)
{
    if (fx == NULL)
        return 1.0f;
    return fx->current_zoom * fx->bop_multiplier;
}
