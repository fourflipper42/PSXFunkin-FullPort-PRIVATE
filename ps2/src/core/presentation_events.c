#include "presentation_events.h"

#include "sserafim_runtime.h"
#include <stdlib.h>
#include <string.h>

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

static Character *target_character(
    PresentationEventTargets *targets,
    const char *target)
{
    if (targets == NULL || target == NULL)
        return NULL;

    if (strcmp(target, "boyfriend") == 0 ||
        strcmp(target, "bf") == 0 ||
        strcmp(target, "player") == 0)
        return targets->player;
    if (strcmp(target, "dad") == 0 ||
        strcmp(target, "opponent") == 0)
        return targets->opponent;
    if (strcmp(target, "girlfriend") == 0 || strcmp(target, "gf") == 0)
        return targets->girlfriend;
    return NULL;
}

static boolean handle_play_animation(
    PresentationEventTargets *targets,
    const char *json)
{
    char target[96];
    char animation[96];
    boolean force;
    Character *character;

    json_string(json, "target", target, sizeof(target), "boyfriend");
    json_string(json, "anim", animation, sizeof(animation), "idle");
    force = json_bool(json, "force", false);

    character = target_character(targets, target);
    if (character != NULL && character->loaded)
        return Character_Play(character, animation, force);

    return targets->stage != NULL &&
        Stage_PlayNamedAnimation(targets->stage, target, animation, force);
}

static boolean handle_target_bop(
    PresentationEventTargets *targets,
    const char *json)
{
    char target[96];
    float rate;
    Character *character;

    json_string(json, "target", target, sizeof(target), "boyfriend");
    rate = json_number(json, "rate", 1.0f);
    if (rate < 0.0f)
        rate = 0.0f;

    character = target_character(targets, target);
    if (character != NULL && character->loaded) {
        character->dance_every = rate;
        return true;
    }

    return targets->stage != NULL &&
        Stage_SetNamedBopSpeed(targets->stage, target, rate);
}

boolean PresentationEvents_Handle(
    PresentationEventTargets *targets,
    const GameplaySongEventFrame *event)
{
    if (targets == NULL || event == NULL || event->name == NULL || event->value == NULL)
        return false;

    if (targets->camera != NULL &&
        CameraEffects_OnSongEvent(
            targets->camera,
            targets->rhythm,
            event->name,
            event->value))
        return true;

    if (SserafimRuntime_HandleEvent(event->name, event->value))
        return true;

    if (strcmp(event->name, "PlayAnimation") == 0)
        return handle_play_animation(targets, event->value);

    if (strcmp(event->name, "SetTargetBopSpeed") == 0)
        return handle_target_bop(targets, event->value);

    return false;
}
