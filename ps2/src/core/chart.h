#ifndef FNF_PS2_CHART_H
#define FNF_PS2_CHART_H

#include "psx.h"

typedef struct Section {
    u16 end;  /* 1/12 steps */
    u16 flag;
} Section;

#define SECTION_FLAG_OPPFOCUS (1u << 15)
#define SECTION_FLAG_BPM_MASK 0x7FFFu

#define NOTE_FLAG_OPPONENT    (1u << 2)
#define NOTE_FLAG_SUSTAIN     (1u << 3)
#define NOTE_FLAG_SUSTAIN_END (1u << 4)
#define NOTE_FLAG_ALT_ANIM    (1u << 5)
#define NOTE_FLAG_MINE        (1u << 6)
#define NOTE_FLAG_HIT         (1u << 7)

typedef struct Note {
    u16 pos; /* 1/12 steps, 0xFFFF terminates the note stream */
    u8 type;
    u8 pad;
} Note;

typedef struct ChartView {
    u8 *data;
    size_t size;
    Section *sections;
    size_t section_count;
    Note *notes;
    size_t note_count;
} ChartView;

typedef enum ChartResult {
    CHART_OK = 0,
    CHART_ERR_NULL,
    CHART_ERR_IO,
    CHART_ERR_ALLOC,
    CHART_ERR_TOO_SMALL,
    CHART_ERR_SECTION_OFFSET,
    CHART_ERR_SECTION_LAYOUT,
    CHART_ERR_NOTE_SENTINEL
} ChartResult;

ChartResult Chart_Parse(ChartView *out, void *data, size_t size);
const char *Chart_ResultString(ChartResult result);

#endif
