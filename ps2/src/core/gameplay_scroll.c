#include "gameplay_scroll.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

#define SCROLL_SIDE_PLAYER   1u
#define SCROLL_SIDE_OPPONENT 2u
#define SCROLL_SIDE_BOTH     3u
#define SCROLL_PI 3.14159265358979323846f

typedef enum ScrollEaseType {
    SCROLL_EASE_LINEAR = 0,
    SCROLL_EASE_SINE,
    SCROLL_EASE_QUAD,
    SCROLL_EASE_CUBE,
    SCROLL_EASE_QUART,
    SCROLL_EASE_QUINT,
    SCROLL_EASE_EXPO,
    SCROLL_EASE_SMOOTH_STEP,
    SCROLL_EASE_SMOOTHER_STEP,
    SCROLL_EASE_ELASTIC,
    SCROLL_EASE_BACK,
    SCROLL_EASE_BOUNCE,
    SCROLL_EASE_CIRC
} ScrollEaseType;

typedef enum ScrollEaseDir {
    SCROLL_EASE_IN = 0,
    SCROLL_EASE_OUT,
    SCROLL_EASE_IN_OUT
} ScrollEaseDir;

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
    size_t n;

    if (json == NULL || key == NULL)
        return NULL;
    n = strlen(key);
    if (n + 3u >= sizeof(needle))
        return NULL;
    needle[0] = '"';
    memcpy(needle + 1, key, n);
    needle[n + 1] = '"';
    needle[n + 2] = '\0';
    found = strstr(json, needle);
    if (found == NULL)
        return NULL;
    colon = strchr(found + n + 2, ':');
    return colon != NULL ? skip_space(colon + 1) : NULL;
}

static float json_number(const char *json, const char *key, float fallback)
{
    const char *value = json_value(json, key);
    char *end;
    float result;
    if (value == NULL)
        return fallback;
    result = strtof(value, &end);
    return end == value ? fallback : result;
}

static boolean json_bool(const char *json, const char *key, boolean fallback)
{
    const char *value = json_value(json, key);
    if (value == NULL)
        return fallback;
    if (strncmp(value, "true", 4) == 0)
        return true;
    if (strncmp(value, "false", 5) == 0)
        return false;
    return fallback;
}

static void json_string(
    const char *json,
    const char *key,
    char *out,
    size_t out_size,
    const char *fallback)
{
    const char *value = json_value(json, key);
    const char *end;
    size_t length;

    if (out == NULL || out_size == 0)
        return;
    if (value == NULL || *value != '"') {
        strncpy(out, fallback != NULL ? fallback : "", out_size - 1);
        out[out_size - 1] = '\0';
        return;
    }
    ++value;
    end = strchr(value, '"');
    if (end == NULL) {
        strncpy(out, fallback != NULL ? fallback : "", out_size - 1);
        out[out_size - 1] = '\0';
        return;
    }
    length = (size_t)(end - value);
    if (length >= out_size)
        length = out_size - 1;
    memcpy(out, value, length);
    out[length] = '\0';
}

static boolean ends_with(const char *text, const char *suffix)
{
    size_t a;
    size_t b;
    if (text == NULL || suffix == NULL)
        return false;
    a = strlen(text);
    b = strlen(suffix);
    return a >= b && strcmp(text + a - b, suffix) == 0;
}

static void parse_ease(
    const char *json,
    u8 *type,
    u8 *dir,
    boolean *instant)
{
    char ease[32];
    char ease_dir[16];
    size_t len;

    *type = SCROLL_EASE_LINEAR;
    *dir = SCROLL_EASE_IN;
    *instant = false;
    json_string(json, "ease", ease, sizeof(ease), "linear");
    json_string(json, "easeDir", ease_dir, sizeof(ease_dir), "In");

    if (strcmp(ease, "INSTANT") == 0) {
        *instant = true;
        return;
    }
    if (ends_with(ease, "InOut")) {
        *dir = SCROLL_EASE_IN_OUT;
        len = strlen(ease);
        ease[len - 5] = '\0';
    } else if (ends_with(ease, "Out")) {
        *dir = SCROLL_EASE_OUT;
        len = strlen(ease);
        ease[len - 3] = '\0';
    } else if (ends_with(ease, "In") && strcmp(ease, "linear") != 0) {
        *dir = SCROLL_EASE_IN;
        len = strlen(ease);
        ease[len - 2] = '\0';
    } else if (strcmp(ease_dir, "Out") == 0) {
        *dir = SCROLL_EASE_OUT;
    } else if (strcmp(ease_dir, "InOut") == 0) {
        *dir = SCROLL_EASE_IN_OUT;
    }

    if (strcmp(ease, "sine") == 0) *type = SCROLL_EASE_SINE;
    else if (strcmp(ease, "quad") == 0) *type = SCROLL_EASE_QUAD;
    else if (strcmp(ease, "cube") == 0) *type = SCROLL_EASE_CUBE;
    else if (strcmp(ease, "quart") == 0) *type = SCROLL_EASE_QUART;
    else if (strcmp(ease, "quint") == 0) *type = SCROLL_EASE_QUINT;
    else if (strcmp(ease, "expo") == 0) *type = SCROLL_EASE_EXPO;
    else if (strcmp(ease, "smoothStep") == 0) *type = SCROLL_EASE_SMOOTH_STEP;
    else if (strcmp(ease, "smootherStep") == 0) *type = SCROLL_EASE_SMOOTHER_STEP;
    else if (strcmp(ease, "elastic") == 0) *type = SCROLL_EASE_ELASTIC;
    else if (strcmp(ease, "back") == 0) *type = SCROLL_EASE_BACK;
    else if (strcmp(ease, "bounce") == 0) *type = SCROLL_EASE_BOUNCE;
    else if (strcmp(ease, "circ") == 0) *type = SCROLL_EASE_CIRC;
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

static float ease_in(u8 type, float t)
{
    const float c1 = 1.70158f;
    const float c3 = c1 + 1.0f;
    switch (type) {
        case SCROLL_EASE_SINE: return 1.0f - cosf((t * SCROLL_PI) * 0.5f);
        case SCROLL_EASE_QUAD: return t * t;
        case SCROLL_EASE_CUBE: return t * t * t;
        case SCROLL_EASE_QUART: return t * t * t * t;
        case SCROLL_EASE_QUINT: return t * t * t * t * t;
        case SCROLL_EASE_EXPO: return t <= 0.0f ? 0.0f : powf(2.0f, 10.0f * t - 10.0f);
        case SCROLL_EASE_SMOOTH_STEP: return t * t * (3.0f - 2.0f * t);
        case SCROLL_EASE_SMOOTHER_STEP: return t * t * t * (t * (t * 6.0f - 15.0f) + 10.0f);
        case SCROLL_EASE_ELASTIC:
            if (t <= 0.0f || t >= 1.0f) return t;
            return -powf(2.0f, 10.0f * t - 10.0f) *
                sinf((t * 10.0f - 10.75f) * ((2.0f * SCROLL_PI) / 3.0f));
        case SCROLL_EASE_BACK: return c3 * t * t * t - c1 * t * t;
        case SCROLL_EASE_CIRC: return 1.0f - sqrtf(1.0f - t * t);
        default: return t;
    }
}

static float apply_ease(u8 type, u8 dir, float t)
{
    float half;
    if (t < 0.0f) t = 0.0f;
    if (t > 1.0f) t = 1.0f;
    if (type == SCROLL_EASE_LINEAR)
        return t;
    if (type == SCROLL_EASE_BOUNCE) {
        if (dir == SCROLL_EASE_OUT) return bounce_out(t);
        if (dir == SCROLL_EASE_IN) return 1.0f - bounce_out(1.0f - t);
        if (t < 0.5f) return (1.0f - bounce_out(1.0f - 2.0f * t)) * 0.5f;
        return (1.0f + bounce_out(2.0f * t - 1.0f)) * 0.5f;
    }
    if (dir == SCROLL_EASE_OUT)
        return 1.0f - ease_in(type, 1.0f - t);
    if (dir == SCROLL_EASE_IN_OUT) {
        if (t < 0.5f) {
            half = ease_in(type, t * 2.0f);
            return half * 0.5f;
        }
        half = ease_in(type, (1.0f - t) * 2.0f);
        return 1.0f - half * 0.5f;
    }
    return ease_in(type, t);
}

static fixed_t float_to_fixed(float value)
{
    return (fixed_t)(value * (float)FIXED_UNIT);
}

static float fixed_to_float(fixed_t value)
{
    return (float)value / (float)FIXED_UNIT;
}

static fixed_t step_duration(const GameplayState *state, float steps)
{
    float units_per_second;
    float seconds;
    if (state == NULL || state->rhythm.step_crochet <= 0)
        return float_to_fixed(steps * 0.125f);
    units_per_second = fixed_to_float(state->rhythm.step_crochet);
    if (units_per_second <= 0.0f)
        return float_to_fixed(steps * 0.125f);
    seconds = (12.0f / units_per_second) * steps;
    return float_to_fixed(seconds);
}

void GameplayScroll_Reset(GameplayState *state)
{
    if (state == NULL)
        return;
    state->player_scroll_speed = state->rhythm.speed;
    state->opponent_scroll_speed = state->rhythm.speed;
    memset(&state->scroll_tween, 0, sizeof(state->scroll_tween));
}

boolean GameplayScroll_HandleEvent(
    GameplayState *state,
    const char *name,
    const char *value_json)
{
    char strumline[24];
    float scroll;
    float duration_steps;
    boolean absolute;
    boolean instant;
    u8 sides = SCROLL_SIDE_BOTH;
    fixed_t target;

    if (state == NULL || name == NULL || value_json == NULL ||
        strcmp(name, "ScrollSpeed") != 0)
        return false;

    if (state->player_scroll_speed <= 0 || state->opponent_scroll_speed <= 0)
        GameplayScroll_Reset(state);

    scroll = json_number(value_json, "scroll", 1.0f);
    duration_steps = json_number(value_json, "duration", 4.0f);
    absolute = json_bool(value_json, "absolute", false);
    json_string(value_json, "strumline", strumline, sizeof(strumline), "both");

    if (strcmp(strumline, "player") == 0)
        sides = SCROLL_SIDE_PLAYER;
    else if (strcmp(strumline, "opponent") == 0)
        sides = SCROLL_SIDE_OPPONENT;

    if (!absolute)
        scroll *= fixed_to_float(state->rhythm.speed);
    if (scroll < 0.1f)
        scroll = 0.1f;
    target = float_to_fixed(scroll);

    state->scroll_tween.start_player = state->player_scroll_speed;
    state->scroll_tween.start_opponent = state->opponent_scroll_speed;
    state->scroll_tween.target_player =
        (sides & SCROLL_SIDE_PLAYER) ? target : state->player_scroll_speed;
    state->scroll_tween.target_opponent =
        (sides & SCROLL_SIDE_OPPONENT) ? target : state->opponent_scroll_speed;
    state->scroll_tween.elapsed = 0;
    state->scroll_tween.duration = step_duration(state, duration_steps);
    state->scroll_tween.side_mask = sides;
    parse_ease(
        value_json,
        &state->scroll_tween.ease_type,
        &state->scroll_tween.ease_dir,
        &instant);

    if (instant || state->scroll_tween.duration <= 0) {
        state->player_scroll_speed = state->scroll_tween.target_player;
        state->opponent_scroll_speed = state->scroll_tween.target_opponent;
        state->scroll_tween.active = false;
    } else {
        state->scroll_tween.active = true;
    }
    return true;
}

void GameplayScroll_Tick(GameplayState *state, fixed_t dt)
{
    float progress;
    float eased;

    if (state == NULL)
        return;
    if (state->player_scroll_speed <= 0 || state->opponent_scroll_speed <= 0)
        GameplayScroll_Reset(state);
    if (!state->scroll_tween.active)
        return;

    state->scroll_tween.elapsed += dt;
    progress = state->scroll_tween.duration > 0
        ? fixed_to_float(state->scroll_tween.elapsed) /
            fixed_to_float(state->scroll_tween.duration)
        : 1.0f;
    if (progress >= 1.0f) {
        state->player_scroll_speed = state->scroll_tween.target_player;
        state->opponent_scroll_speed = state->scroll_tween.target_opponent;
        state->scroll_tween.active = false;
        return;
    }

    eased = apply_ease(
        state->scroll_tween.ease_type,
        state->scroll_tween.ease_dir,
        progress);
    if (state->scroll_tween.side_mask & SCROLL_SIDE_PLAYER) {
        state->player_scroll_speed = state->scroll_tween.start_player +
            (fixed_t)((float)(state->scroll_tween.target_player -
                state->scroll_tween.start_player) * eased);
    }
    if (state->scroll_tween.side_mask & SCROLL_SIDE_OPPONENT) {
        state->opponent_scroll_speed = state->scroll_tween.start_opponent +
            (fixed_t)((float)(state->scroll_tween.target_opponent -
                state->scroll_tween.start_opponent) * eased);
    }
}

fixed_t Gameplay_NoteSpeedForSide(const GameplayState *state, boolean opponent)
{
    fixed_t scroll;
    fixed_t ratio;

    if (state == NULL)
        return 0;
    scroll = opponent ? state->opponent_scroll_speed : state->player_scroll_speed;
    if (scroll <= 0)
        scroll = state->rhythm.speed;
    if (state->rhythm.speed <= 0)
        return state->rhythm.note_speed;
    ratio = FIXED_DIV(scroll, state->rhythm.speed);
    return FIXED_MUL(state->rhythm.note_speed, ratio);
}
