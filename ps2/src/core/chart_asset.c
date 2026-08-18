#include "chart_asset.h"

#include "asset_file.h"
#include "mem.h"
#include <string.h>

ChartResult ChartAsset_Load(ChartAsset *asset, const char *path)
{
    AssetFile file;
    ChartResult result;
    size_t got;

    if (asset == NULL || path == NULL)
        return CHART_ERR_NULL;

    memset(asset, 0, sizeof(*asset));
    memset(&file, 0, sizeof(file));

    if (!AssetFile_Open(&file, path))
        return CHART_ERR_IO;
    if (AssetFile_Size(&file) == 0) {
        AssetFile_Close(&file);
        return CHART_ERR_TOO_SMALL;
    }

    asset->size = AssetFile_Size(&file);
    asset->data = Mem_Alloc(asset->size);
    if (asset->data == NULL) {
        AssetFile_Close(&file);
        memset(asset, 0, sizeof(*asset));
        return CHART_ERR_ALLOC;
    }

    got = AssetFile_Read(&file, asset->data, asset->size);
    AssetFile_Close(&file);
    if (got != asset->size) {
        ChartAsset_Free(asset);
        return CHART_ERR_IO;
    }

    result = Chart_Parse(&asset->view, asset->data, asset->size);
    if (result != CHART_OK)
        ChartAsset_Free(asset);
    return result;
}

void ChartAsset_Free(ChartAsset *asset)
{
    if (asset == NULL)
        return;
    if (asset->data != NULL)
        Mem_Free(asset->data);
    memset(asset, 0, sizeof(*asset));
}
