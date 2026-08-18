#define SESSION_RUNTIME_IMPLEMENTATION
#include "session_runtime.h"

#include "blazin_runtime.h"
#include "cutscene_controller.h"
#include "weekend1_runtime.h"

void SessionRuntime_AfterGameplayFrameScaled(
    SessionRuntime *session,
    GameplayState *game,
    fixed_t elapsed)
{
    if (CutsceneController_Active()) {
        /* Native cutscene characters/stage props still need real-time animation
         * even though chart/audio gameplay is gated. Video frames remain driven
         * independently by their PCM clock. */
        timer_presentation_dt = elapsed;
        CutsceneController_Tick();

        if (session != NULL) {
            if (CutsceneController_Active()) {
                float x = CutsceneController_CameraX();
                float y = CutsceneController_CameraY();
                session->camera_movement.offset_x = x;
                session->camera_movement.offset_y = y;
                session->camera_movement.target_x = x;
                session->camera_movement.target_y = y;
            } else {
                /* Let the normal movement smoother return from the final
                 * cutscene camera position instead of snapping on countdown. */
                session->camera_movement.target_x = 0.0f;
                session->camera_movement.target_y = 0.0f;
            }
        }
        return;
    }

    if (session != NULL && session->song_active)
        timer_presentation_dt = Gammod_PresentationDelta(&session->gammod, elapsed);
    else
        timer_presentation_dt = elapsed;

    /* 2hot can cancel/repair note outcomes, so it must run before generic
     * combo/HUD/note-kind consumers inspect the frame. */
    if (session != NULL && session->song_active)
        Weekend1Runtime_Tick(game, &session->note_kinds, elapsed);

    SessionRuntime_AfterGameplayFrame(session, game, elapsed);

    /* Blazin choreography consumes the finalized hit/miss frame after generic
     * note-kind resolution. Weekend-1 kinds suppress ordinary sing animations,
     * so these paired fight animations remain authoritative. */
    if (session != NULL && session->song_active)
        BlazinRuntime_Tick(game, &session->note_kinds);
}
