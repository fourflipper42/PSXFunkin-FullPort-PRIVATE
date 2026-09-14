#include "menu_sound.h"
#include "io.h"
#include "mem.h"
#include "main.h"

/* Menu owns voices 0..3 and SPU RAM from 0x1010 while loaded. The base
 * engine otherwise uses CD XA; no SPU allocator or music voices are active. */
static u32 addresses[3];
static unsigned int voice;
static u32 ReadBE(const u8 *p)
{
    return ((u32)p[0] << 24) | ((u32)p[1] << 16) | ((u32)p[2] << 8) | p[3];
}
void MenuSound_Free(void)
{
    SpuSetKey(SPU_OFF, 15);
    memset(addresses, 0, sizeof(addresses));
}
void MenuSound_Load(void)
{
    static const char *paths[] = {"\\MENU\\SCROLL.VAG;1", "\\MENU\\CONFIRM.VAG;1", "\\MENU\\CANCEL.VAG;1"};
    u32 address = 0x1010;
    unsigned int i;
    MenuSound_Free();
    voice = 0;
    SpuSetTransferMode(SPU_TRANSFER_BY_DMA);
    for (i = 0; i < COUNT_OF(paths); i++) {
        CdlFILE file;
        u8 *data;
        u32 size;
        IO_FindFile(&file, paths[i]);
        data = (u8*)IO_ReadFile(&file);
        size = file.size >= 48 ? ReadBE(data + 12) : 0;
        if (!size || memcmp(data, "VAGp", 4) || size % 16 || size > file.size - 48 ||
            ReadBE(data + 16) != 44100 || size > 0x80000 - address) {
            sprintf(error_msg, "[MenuSound] invalid VAG bank");
            ErrorLock();
            return;
        }
        addresses[i] = address;
        SpuSetTransferStartAddr(address);
        SpuWrite(data + 48, size);
        SpuIsTransferCompleted(SPU_TRANSFER_WAIT);
        Mem_Free(data);
        address = (address + size + 63) & ~63;
    }
}
void MenuSound_Play(MenuSound sound)
{
    SpuVoiceAttr attr;
    if ((unsigned int)sound >= COUNT_OF(addresses) || !addresses[sound]) return;
    memset(&attr, 0, sizeof(attr));
    attr.voice = 1 << voice;
    voice = (voice + 1) & 3;
    attr.mask = SPU_VOICE_VOLL | SPU_VOICE_VOLR | SPU_VOICE_PITCH | SPU_VOICE_WDSA |
        SPU_VOICE_ADSR_ADSR1 | SPU_VOICE_ADSR_ADSR2;
    attr.volume.left = attr.volume.right = sound == MenuSound_Confirm ? 0x2CCC : 0x1999;
    attr.pitch = 0x1000;
    attr.addr = addresses[sound];
    attr.adsr1 = 0x000F; /* Immediate attack, full sustain. */
    attr.adsr2 = 0;
    SpuSetKey(SPU_OFF, attr.voice);
    SpuSetVoiceAttr(&attr);
    SpuSetKey(SPU_ON, attr.voice);
}
