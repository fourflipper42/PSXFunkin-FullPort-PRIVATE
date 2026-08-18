#include "character.h"

#include "presentation_registry.h"

boolean Character_LoadCore(
    GSGLOBAL *gs,
    Character *character,
    const char *config_path,
    const char *texture_path,
    const char *frames_path);
void Character_ForgetCore(Character *character);

boolean Character_Load(
    GSGLOBAL *gs,
    Character *character,
    const char *config_path,
    const char *texture_path,
    const char *frames_path)
{
    boolean result = Character_LoadCore(
        gs, character, config_path, texture_path, frames_path);
    PresentationRegistry_RegisterCharacter(result ? character : NULL);
    return result;
}

void Character_Forget(Character *character)
{
    PresentationRegistry_UnregisterCharacter(character);
    Character_ForgetCore(character);
}
