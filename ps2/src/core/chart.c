#include "chart.h"
#include <string.h>

static u16 read_u16_le(const u8 *p)
{
    return (u16)((u16)p[0] | ((u16)p[1] << 8));
}

ChartResult Chart_Parse(ChartView *out, const void *data, size_t size)
{
    const u8 *bytes;
    size_t note_offset;
    size_t max_notes;
    size_t i;

    if (out == NULL || data == NULL)
        return CHART_ERR_NULL;

    memset(out, 0, sizeof(*out));
    if (size < 2u + sizeof(Section) + sizeof(Note))
        return CHART_ERR_TOO_SMALL;

    bytes = (const u8 *)data;
    note_offset = (size_t)read_u16_le(bytes);

    if (note_offset < 2u || note_offset > size - sizeof(Note))
        return CHART_ERR_SECTION_OFFSET;

    if (((note_offset - 2u) % sizeof(Section)) != 0u)
        return CHART_ERR_SECTION_LAYOUT;

    out->data = bytes;
    out->size = size;
    out->sections = (const Section *)(bytes + 2u);
    out->section_count = (note_offset - 2u) / sizeof(Section);
    out->notes = (const Note *)(bytes + note_offset);

    max_notes = (size - note_offset) / sizeof(Note);
    for (i = 0; i < max_notes; ++i) {
        if (out->notes[i].pos == 0xFFFFu) {
            out->note_count = i;
            return CHART_OK;
        }
    }

    memset(out, 0, sizeof(*out));
    return CHART_ERR_NOTE_SENTINEL;
}

const char *Chart_ResultString(ChartResult result)
{
    switch (result) {
        case CHART_OK: return "ok";
        case CHART_ERR_NULL: return "null argument";
        case CHART_ERR_IO: return "chart I/O error";
        case CHART_ERR_ALLOC: return "chart allocation failed";
        case CHART_ERR_TOO_SMALL: return "chart too small";
        case CHART_ERR_SECTION_OFFSET: return "invalid note offset";
        case CHART_ERR_SECTION_LAYOUT: return "invalid section layout";
        case CHART_ERR_NOTE_SENTINEL: return "missing note sentinel";
        default: return "unknown chart error";
    }
}
