#define SESSION_RUNTIME_IMPLEMENTATION
#include "session_runtime.h"

#include "presentation_registry.h"
#include "sserafim_runtime.h"

void SessionRuntime_PlayHitAnimationsCore(
    SessionRuntime *session,
    Character *player,
    Character *opponent);

void SessionRuntime_PlayHitAnimations(
    SessionRuntime *session,
    Character *player,
    Character *opponent)
{
    if (session == NULL || !session->song_active)
        return;

    if (SserafimRuntime_Active()) {
        SserafimRuntime_PlayHitAnimations(
            session->active_game,
            player,
            opponent,
            PresentationRegistry_Girlfriend());
        return;
    }

    SessionRuntime_PlayHitAnimationsCore(session, player, opponent);
}
