#define NEWLIB_PORT_AWARE

#include "save_data.h"

#include <fileio.h>
#include <fcntl.h>
#include <libmc.h>
#include <loadfile.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define SAVE_DIRECTORY "mc0:FUNKINPS2"
#define SAVE_PATH      "mc0:FUNKINPS2/SAVE.BIN"

static boolean g_memcard_ready;

static u32 save_checksum_bytes(const void *data, size_t size)
{
    const u8 *bytes = (const u8 *)data;
    u32 hash = 2166136261u;
    size_t i;

    for (i = 0; i < size; ++i) {
        hash ^= bytes[i];
        hash *= 16777619u;
    }
    return hash;
}

static u32 save_checksum(const FunkinSaveData *data)
{
    FunkinSaveData copy;

    if (data == NULL)
        return 0;
    copy = *data;
    copy.checksum = 0;
    return save_checksum_bytes(&copy, sizeof(copy));
}

void SaveData_Defaults(FunkinSaveData *data)
{
    if (data == NULL)
        return;

    memset(data, 0, sizeof(*data));
    memcpy(data->magic, "FPS2", 4);
    data->version = FNF_SAVE_VERSION;
    data->size = sizeof(*data);

    data->settings_flags =
        SAVE_FLAG_CAMERA_MOVEMENT |
        SAVE_FLAG_COMBO_POPUPS |
        SAVE_FLAG_COMBO_SWOOSH |
        SAVE_FLAG_COMBO_SOUND |
        SAVE_FLAG_HUD_FC_INDICATOR |
        SAVE_FLAG_HUD_ICON_BOUNCE |
        SAVE_FLAG_HUD_SCORE_BOUNCE;
    data->health_drain_level = 6; /* AUTO PRO, matching the supplied mod. */
    data->camera_movement_intensity = 80;
    data->combo_swoosh_threshold = 1;
    data->hud_layout = 0;
    data->checksum = save_checksum(data);
}

boolean SaveData_Init(void)
{
    int ret;
    int type = 0;
    int free_blocks = 0;
    int formatted = 0;

    g_memcard_ready = false;

    /* Pad_Init already loads SIO2MAN. Use the matching ROM memory-card stack
     * rather than loading XSIO2MAN on top of an active pad driver. */
    ret = SifLoadModule("rom0:MCMAN", 0, NULL);
    if (ret < 0)
        printf("[PS2] MCMAN load returned %d\n", ret);
    ret = SifLoadModule("rom0:MCSERV", 0, NULL);
    if (ret < 0)
        printf("[PS2] MCSERV load returned %d\n", ret);

    if (mcInit(MC_TYPE_MC) < 0) {
        printf("[PS2] memory card RPC unavailable\n");
        return false;
    }

    mcGetInfo(0, 0, &type, &free_blocks, &formatted);
    mcSync(0, NULL, &ret);
    if (ret <= -10) {
        printf("[PS2] no memory card in slot 1 (%d)\n", ret);
        return false;
    }

    g_memcard_ready = true;
    printf("[PS2] memory card slot 1 ready: type=%d free=%d format=%d\n",
        type, free_blocks, formatted);
    return true;
}

boolean SaveData_Load(FunkinSaveData *data)
{
    FunkinSaveData loaded;
    int fd;
    int got;

    if (data == NULL)
        return false;

    SaveData_Defaults(data);
    if (!g_memcard_ready)
        return false;

    fd = open(SAVE_PATH, O_RDONLY);
    if (fd < 0) {
        printf("[PS2] no existing save, using defaults\n");
        return false;
    }

    got = read(fd, &loaded, sizeof(loaded));
    close(fd);
    if (got != (int)sizeof(loaded) ||
        memcmp(loaded.magic, "FPS2", 4) != 0 ||
        loaded.version != FNF_SAVE_VERSION ||
        loaded.size != sizeof(loaded) ||
        loaded.checksum != save_checksum(&loaded)) {
        printf("[PS2] save invalid or incompatible, using defaults\n");
        return false;
    }

    *data = loaded;
    printf("[PS2] save loaded\n");
    return true;
}

boolean SaveData_Write(const FunkinSaveData *data)
{
    FunkinSaveData out;
    int fd;
    int wrote;

    if (data == NULL || !g_memcard_ready)
        return false;

    out = *data;
    memcpy(out.magic, "FPS2", 4);
    out.version = FNF_SAVE_VERSION;
    out.size = sizeof(out);
    out.checksum = save_checksum(&out);

    /* Existing directories return an error here; that is harmless. */
    mkdir(SAVE_DIRECTORY, 0777);
    fd = open(SAVE_PATH, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (fd < 0) {
        printf("[PS2] save open failed\n");
        return false;
    }

    wrote = write(fd, &out, sizeof(out));
    close(fd);
    if (wrote != (int)sizeof(out)) {
        printf("[PS2] save write short: %d/%u\n", wrote, (unsigned)sizeof(out));
        return false;
    }

    printf("[PS2] save written\n");
    return true;
}

void SaveData_GetProgression(const FunkinSaveData *data, ProgressionState *progression)
{
    if (progression == NULL)
        return;
    Progression_Reset(progression);
    if (data != NULL)
        progression->completed_story_levels = data->completed_story_levels;
}

void SaveData_SetProgression(FunkinSaveData *data, const ProgressionState *progression)
{
    if (data == NULL || progression == NULL)
        return;
    data->completed_story_levels = progression->completed_story_levels;
}
