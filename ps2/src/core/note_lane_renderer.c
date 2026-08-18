#include "note_lane_renderer.h"

#include "gameplay_scroll.h"
#include "timer.h"
#include <string.h>

#define RECEPTOR_Y 70.0f
#define OPPONENT_X 64.0f
#define PLAYER_X   408.0f
#define CENTER_PLAYER_X 236.0f
#define LANE_GAP   56.0f
#define CONFIRM_FRAMES 7

static u8 confirm_frames[2][4];
static u32 animation_tick;
static boolean hide_opponent_strumline;
static boolean center_player_strumline;

static float lane_center(boolean opponent, u8 lane)
{
    float start;
    if (opponent)
        start = OPPONENT_X;
    else
        start = center_player_strumline ? CENTER_PLAYER_X : PLAYER_X;
    return start + (float)(lane & 3) * LANE_GAP;
}

static boolean lane_held(const Pad *pad, u8 lane)
{
    static const u16 masks[4] = {
        INPUT_LEFT, INPUT_DOWN, INPUT_UP, INPUT_RIGHT
    };
    return pad != NULL && (pad->held & masks[lane & 3]) != 0;
}

static ReceptorVisualState receptor_state(
    boolean opponent,
    u8 lane,
    const Pad *pad)
{
    u8 side = opponent ? 0 : 1;

    if (confirm_frames[side][lane] != 0) {
        if (!opponent && lane_held(pad, lane))
            return RECEPTOR_CONFIRM_HOLD;
        return RECEPTOR_CONFIRM;
    }
    if (!opponent && lane_held(pad, lane))
        return RECEPTOR_PRESS;
    return RECEPTOR_STATIC;
}

void NoteLaneRenderer_Reset(void)
{
    memset(confirm_frames, 0, sizeof(confirm_frames));
    animation_tick = 0;
    /* Layout is song state, not animation state. Weekend1Runtime_EndSong()
     * explicitly restores the normal layout when leaving Blazin. */
}

void NoteLaneRenderer_SetLayout(boolean hide_opponent, boolean center_player)
{
    hide_opponent_strumline = hide_opponent;
    center_player_strumline = center_player;
}

void NoteLaneRenderer_Tick(GameplayState *game, const Pad *pad)
{
    int side;
    int lane;
    u8 player_hits;
    u8 opponent_hits;
    u8 event_index;
    fixed_t event_dt;

    (void)pad;
    ++animation_tick;

    for (side = 0; side < 2; ++side) {
        for (lane = 0; lane < 4; ++lane) {
            if (confirm_frames[side][lane] != 0)
                --confirm_frames[side][lane];
        }
    }

    if (game == NULL)
        return;

    if (!game->block_scroll_events) {
        for (event_index = 0;
            event_index < game->events.song_event_count;
            ++event_index) {
            const GameplaySongEventFrame *event =
                &game->events.song_events[event_index];
            GameplayScroll_HandleEvent(game, event->name, event->value);
        }
    }
    event_dt = timer_dt;
    if (game->event_time_scale > 0)
        event_dt = FIXED_MUL(event_dt, game->event_time_scale);
    GameplayScroll_Tick(game, event_dt);

    player_hits = game->events.player_hit_mask;
    opponent_hits = game->events.opponent_hit_mask;
    for (lane = 0; lane < 4; ++lane) {
        if (opponent_hits & (1u << lane))
            confirm_frames[0][lane] = CONFIRM_FRAMES;
        if (player_hits & (1u << lane))
            confirm_frames[1][lane] = CONFIRM_FRAMES;
    }
}

static float note_y(
    const GameplayState *game,
    const Note *note,
    boolean opponent)
{
    fixed_t delta = Gameplay_NoteDelta(game, note);
    fixed_t speed = Gameplay_NoteSpeedForSide(game, opponent);
    fixed_t pixel_delta = FIXED_MUL(speed, delta);
    return RECEPTOR_Y + (float)pixel_delta / (float)FIXED_UNIT;
}

static float sustain_step_height(
    const GameplayState *game,
    boolean opponent)
{
    fixed_t quarter_step = (fixed_t)12 << FIXED_SHIFT;
    fixed_t speed = Gameplay_NoteSpeedForSide(game, opponent);
    fixed_t pixels = FIXED_MUL(speed, quarter_step);
    float value = (float)pixels / (float)FIXED_UNIT;
    if (value < 4.0f)
        value = 4.0f;
    return value;
}

void NoteLaneRenderer_Draw(
    GSGLOBAL *gs,
    const NoteStyle *style,
    const GameplayState *game,
    const Pad *pad)
{
    const u64 white = GS_SETREG_RGBAQ(0x80, 0x80, 0x80, 0x80, 0x00);
    const u64 mine_tint = GS_SETREG_RGBAQ(0x28, 0x28, 0x28, 0x80, 0x00);
    const ChartView *chart;
    size_t i;
    int lane;

    if (gs == NULL || style == NULL || !style->loaded ||
        game == NULL || !game->loaded)
        return;

    chart = &game->chart.view;

    for (i = game->first_note; i < chart->note_count; ++i) {
        const Note *note = &chart->notes[i];
        boolean opponent;
        float step_height;
        float y;
        float x;

        if ((note->type & NOTE_FLAG_HIT) || !(note->type & NOTE_FLAG_SUSTAIN))
            continue;

        opponent = (note->type & NOTE_FLAG_OPPONENT) != 0;
        if (opponent && hide_opponent_strumline)
            continue;
        y = note_y(game, note, opponent);
        if (y < -64.0f || y > 424.0f)
            continue;

        step_height = sustain_step_height(game, opponent);
        lane = note->type & 3;
        x = lane_center(opponent, (u8)lane);

        NoteStyle_DrawHoldPiece(
            gs, style, (u8)lane,
            x, y - step_height,
            step_height + 1.0f,
            false, 3, white);

        if (note->type & NOTE_FLAG_SUSTAIN_END) {
            NoteStyle_DrawHoldPiece(
                gs, style, (u8)lane,
                x, y - step_height * 0.10f,
                step_height * 0.90f,
                true, 4, white);
        }
    }

    for (i = game->first_note; i < chart->note_count; ++i) {
        const Note *note = &chart->notes[i];
        boolean opponent;
        float y;
        float x;
        u64 color;

        if ((note->type & NOTE_FLAG_HIT) || (note->type & NOTE_FLAG_SUSTAIN))
            continue;

        opponent = (note->type & NOTE_FLAG_OPPONENT) != 0;
        if (opponent && hide_opponent_strumline)
            continue;
        y = note_y(game, note, opponent);
        if (y < -64.0f || y > 424.0f)
            continue;

        lane = note->type & 3;
        x = lane_center(opponent, (u8)lane);
        color = (note->type & NOTE_FLAG_MINE) ? mine_tint : white;
        NoteStyle_DrawTap(gs, style, (u8)lane, x, y, 5, color);
    }

    for (lane = 0; lane < 4; ++lane) {
        if (!hide_opponent_strumline) {
            NoteStyle_DrawReceptor(
                gs, style, (u8)lane,
                receptor_state(true, (u8)lane, pad),
                animation_tick,
                lane_center(true, (u8)lane), RECEPTOR_Y,
                7, white);
        }
        NoteStyle_DrawReceptor(
            gs, style, (u8)lane,
            receptor_state(false, (u8)lane, pad),
            animation_tick,
            lane_center(false, (u8)lane), RECEPTOR_Y,
            7, white);
    }
}
