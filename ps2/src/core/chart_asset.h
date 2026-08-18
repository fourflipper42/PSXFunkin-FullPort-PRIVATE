#ifndef FNF_PS2_CHART_ASSET_H
#define FNF_PS2_CHART_ASSET_H

#include "chart.h"

typedef struct ChartAsset {
    void *data;
    size_t size;
    ChartView view;
} ChartAsset;

ChartResult ChartAsset_Load(ChartAsset *asset, const char *path);
void ChartAsset_Free(ChartAsset *asset);

#endif
