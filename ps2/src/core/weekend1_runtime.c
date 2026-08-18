#include "weekend1_runtime.h"

#include "mem.h"
#include "note_lane_renderer.h"
#include <string.h>

#define WEEKEND1_CAN_DAMAGE 5000
#define WEEKEND1_HEALTH_MAX 20000

static boolean g_twohot;
static u8 *g_processed;
static size_t g_processed_count;
static fixed_t g_gun_timer;
static fixed_t g_flash_timer;
static u16 g_arcing_cans;
static s16 g_previous_health;
static boolean g_special_death;

static boolean kind_is(
    const NoteKindRuntime *runtime,
    const Note *note,
    const char *name)
{
    return runtime != NULL && runtime->loaded && note != NULL &&
        NoteKinds_NameEquals(&runtime->table, note->pad, name);
}

static boolean is_fire_kind(const NoteKindRuntime *runtime, const Note *note)
{
    return kind_is(runtime, note, "weekend-1-firegun") ||
        kind_is(runtime, note, "weekend-1-firegun-hip") ||
        kind_is(runtime, note, "weekend-1-firegun-far");
}

static s32 scaled_health(const RhythmState *rhythm, s32 amount, boolean gain)
{
    fixed_t multiplier;
    if (rhythm == NULL)
        return amount;
    multiplier = gain ? rhythm->health_gain_mult : rhythm->health_loss_mult;
    if (multiplier < 0)
        multiplier = 0;
    return (s32)(((s64)amount * multiplier) >> FIXED_SHIFT);
}

static void set_health(GameplayState *game, s32 health)
{
    if (game == NULL)
        return;
    if (health > WEEKEND1_HEALTH_MAX) health = WEEKEND1_HEALTH_MAX;
    if (health < 0) health = 0;
    game->rhythm.health = (s16)health;
}

static void revive_if_corrected(GameplayState *game)
{
    if (game == NULL || game->rhythm.health <= 0 || !game->dead)
        return;
    game->dead = false;
    game->paused = false;
    game->events.player_died = false;
    if (game->audio_started && SongStream_Paused(&game->song))
        SongStream_Resume(&game->song);
}

static void suppress_normal_head_miss(GameplayState *game)
{
    s32 health;
    s32 undo;
    if (game == NULL)
        return;

    /* Gameplay_CheckHealth clamps a lethal ordinary miss to zero. In that
     * case restore the health snapshot from the preceding frame, because the
     * Weekend 1 script explicitly sets this note's normal healthChange to 0. */
    if (game->dead)
        health = g_previous_health;
    else {
        undo = -scaled_health(&game->rhythm, -1000, false);
        health = (s32)game->rhythm.health + undo;
    }
    set_health(game, health);
    revive_if_corrected(game);
}

static void take_can_damage(GameplayState *game)
{
    s32 health;
    if (game == NULL)
        return;
    health = (s32)game->rhythm.health - WEEKEND1_CAN_DAMAGE;
    set_health(game, health);
    if (game->rhythm.health <= 0) {
        g_special_death = true;
        game->dead = true;
        game->paused = true;
        game->events.player_died = true;
        if (game->audio_started && !SongStream_Paused(&game->song))
            SongStream_Pause(&game->song);
    }
}

static void undo_uncocked_fire_hit(GameplayState *game, Note *note)
{
    HitRating rating;
    s32 score_gain;
    s32 health_gain;
    u8 lane;
    static const s32 vanilla_scores[4] = {35, 20, 10, 5};
    static const s32 kade_scores[4] = {35, 20, 0, -30};

    if (game == NULL || note == NULL)
        return;

    rating = Rhythm_ClassifyHit(
        &game->rhythm,
        game->note_scroll - ((fixed_t)note->pos << FIXED_SHIFT));
    if (game->rhythm.judged_notes != 0)
        --game->rhythm.judged_notes;
    if (game->rhythm.rating_counts[(int)rating] != 0)
        --game->rhythm.rating_counts[(int)rating];

    score_gain = game->rhythm.kade
        ? kade_scores[(int)rating]
        : vanilla_scores[(int)rating];
    game->rhythm.score -= score_gain;

    if (!game->rhythm.kade) {
        health_gain = scaled_health(&game->rhythm, 230, true);
        set_health(game, (s32)game->rhythm.health - health_gain);
        if (game->rhythm.combo != 0)
            --game->rhythm.combo;
    } else if (rating != HIT_SHIT) {
        /* The PS2 port normally runs modern, non-Kade scoring. Keep this
         * fallback conservative for dev charts using the legacy switch. */
        if (game->rhythm.combo != 0)
            --game->rhythm.combo;
    }

    note->type &= (u8)~NOTE_FLAG_HIT;
    lane = note->type & 3u;
    game->events.player_hit_mask &= (u8)~(1u << lane);
    SongStream_SetVoices(&game->song, false);
}

void Weekend1Runtime_EndSong(void)
{
    if (g_processed != NULL)
        Mem_Free(g_processed);
    g_processed = NULL;
    g_processed_count = 0;
    g_twohot = false;
    g_gun_timer = 0;
    g_flash_timer = 0;
    g_arcing_cans = 0;
    g_previous_health = 0;
    g_special_death = false;
    NoteLaneRenderer_SetLayout(false, false);
}

void Weekend1Runtime_BeginSong(
    const char *song_id,
    GameplayState *game,
    const NoteKindRuntime *note_kinds)
{
    (void)note_kinds;
    Weekend1Runtime_EndSong();
    if (song_id == NULL || game == NULL || !game->loaded)
        return;

    if (strcmp(song_id, "blazin") == 0) {
        /* The official script permanently hides the opponent strumline and
         * centers the player's four arrows for this song. */
        NoteLaneRenderer_SetLayout(true, true);
        return;
    }

    if (strcmp(song_id, "2hot") != 0)
        return;

    g_twohot = true;
    g_previous_health = game->rhythm.health;
    g_processed_count = game->chart.view.note_count;
    if (g_processed_count != 0) {
        g_processed = (u8 *)Mem_Alloc(g_processed_count);
        if (g_processed != NULL)
            memset(g_processed, 0, g_processed_count);
        else
            g_processed_count = 0;
    }
}

void Weekend1Runtime_Tick(
    GameplayState *game,
    const NoteKindRuntime *note_kinds,
    fixed_t elapsed)
{
    ChartView *chart;
    size_t i;

    if (!g_twohot || game == NULL || !game->loaded ||
        note_kinds == NULL || !note_kinds->loaded)
        return;

    if (g_gun_timer > 0) {
        g_gun_timer -= elapsed;
        if (g_gun_timer < 0) g_gun_timer = 0;
    }
    if (g_flash_timer > 0) {
        g_flash_timer -= elapsed;
        if (g_flash_timer < 0) g_flash_timer = 0;
    }

    chart = &game->chart.view;
    for (i = 0; i < chart->note_count; ++i) {
        Note *note = &chart->notes[i];
        fixed_t fp;
        fixed_t safe;
        boolean opponent;
        boolean late_miss;
        boolean special;

        if (!(note->type & NOTE_FLAG_HIT) || (note->type & NOTE_FLAG_SUSTAIN))
            continue;
        if (g_processed != NULL && i < g_processed_count && g_processed[i])
            continue;

        special = kind_is(note_kinds, note, "weekend-1-lightcan") ||
            kind_is(note_kinds, note, "weekend-1-kickcan") ||
            kind_is(note_kinds, note, "weekend-1-kneecan") ||
            kind_is(note_kinds, note, "weekend-1-cockgun") ||
            is_fire_kind(note_kinds, note);
        if (!special)
            continue;

        opponent = (note->type & NOTE_FLAG_OPPONENT) != 0;
        fp = (fixed_t)note->pos << FIXED_SHIFT;
        safe = game->rhythm.late_safe;
        late_miss = !opponent && fp + safe < game->note_scroll;

        if (kind_is(note_kinds, note, "weekend-1-kickcan")) {
            if (!late_miss)
                ++g_arcing_cans;
        } else if (kind_is(note_kinds, note, "weekend-1-cockgun")) {
            if (late_miss) {
                suppress_normal_head_miss(game);
                g_gun_timer = 0;
            } else if (!opponent) {
                g_gun_timer = FIXED_DEC(1, 1);
            }
        } else if (is_fire_kind(note_kinds, note) && !opponent) {
            if (late_miss) {
                suppress_normal_head_miss(game);
                g_gun_timer = 0;
                if (g_arcing_cans != 0)
                    --g_arcing_cans;
                take_can_damage(game);
            } else if (kind_is(note_kinds, note, "weekend-1-firegun")) {
                if (g_gun_timer > 0) {
                    g_gun_timer = 0;
                    if (g_arcing_cans != 0)
                        --g_arcing_cans;
                    g_flash_timer = FIXED_DEC(1, 10);
                } else {
                    /* Source cancels the hit entirely when the gun was not
                     * cocked. Undo the normal judgement and leave the note live
                     * so it can still be hit or eventually miss normally. */
                    undo_uncocked_fire_hit(game, note);
                    continue;
                }
            }
        }

        if (g_processed != NULL && i < g_processed_count)
            g_processed[i] = 1;
    }

    g_previous_health = game->rhythm.health;
}

boolean Weekend1Runtime_CanFlash(void)
{
    return g_twohot && g_flash_timer > 0;
}

boolean Weekend1Runtime_SpecialDeath(void)
{
    return g_twohot && g_special_death;
}
