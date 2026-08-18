#define SESSION_RUNTIME_IMPLEMENTATION
#include "session_runtime.h"

void SessionRuntime_AfterGameplayFrameScaled(
    SessionRuntime *session,
    GameplayState *game,
    fixed_t elapsed)
{
    if (session != NULL && session->song_active)
        timer_presentation_dt = Gammod_PresentationDelta(&session->gammod, elapsed);
    else
        timer_presentation_dt = elapsed;

    SessionRuntime_AfterGameplayFrame(session, game, elapsed);
}
