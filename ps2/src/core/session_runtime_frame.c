#define SESSION_RUNTIME_IMPLEMENTATION
#include "session_runtime.h"

#include "blazin_runtime.h"
#include "cutscene_controller.h"
#include "darnell_intro_visual.h"
#include "weekend1_runtime.h"

void SessionRuntime_AfterGameplayFrameScaled(
    SessionRuntime *session,
    GameplayState *game,
    fixed_t elapsed)
{
    /* This self-arms only for the Darnell song while the native Story cutscene
     * is active, and also tears itself down on the first frame after a skip. */
    DarnellIntroVisual_AutoTick(elapsed);

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

    if (session != NULL && session->song_active)
        Weekend1Runtime_Tick(game, &session->note_kinds, elapsed);

    SessionRuntime_AfterGameplayFrame(session, game, elapsed);

    if (session != NULL && session->song_active)
        BlazinRuntime_Tick(game, &session->note_kinds);
}
